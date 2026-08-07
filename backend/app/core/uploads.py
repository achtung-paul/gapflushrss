# Shared validation and streaming helpers for image uploads. Both image
# routers (api/images.py's Commodity assembly photo and
# api/analysis_images.py's per-Analysis gallery) had identical copies of
# this logic, so it lives here once.
#
# Two things this guards against, both of which the original
# "content_type.startswith('image/')" check missed:
#
# 1. Size. The whole upload is read into memory before it goes to MinIO,
#    so an unbounded read is a straightforward way to exhaust the
#    backend's memory. Nginx caps the request body too (see
#    nginx/nginx.conf) -- this is the second half of that, so the limit
#    still holds if the app is ever reached without nginx in front.
#
# 2. What the file actually *is*. content_type comes from the client and
#    is trivially forged, so it can't be trusted on its own. We sniff the
#    real type from the file's leading bytes and store that instead. This
#    matters most for SVG: an SVG can contain <script>, and the download
#    route serves these files inline from the app's own origin, so a
#    forged "image/svg+xml" upload would have been stored XSS. SVG is
#    deliberately absent from ALLOWED_IMAGE_TYPES -- the app only ever
#    displays photographs, so there's nothing to lose by refusing it.

from fastapi import HTTPException, UploadFile, status

# The real upload limit. nginx is configured 5 MB above this on purpose
# (see nginx/nginx.conf) so that this check is the one that rejects an
# over-sized file -- it can return a JSON message naming the limit, while
# nginx can only return a bare HTML error page. Raising this means raising
# nginx's cap too, or nginx starts rejecting first and the clearer message
# stops being reached.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Raster formats only, on purpose -- see the SVG note above.
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# File extension to use for each accepted type, so the object key's
# extension comes from what the file *is* rather than from the
# client-supplied filename.
EXTENSION_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def sniff_image_type(data: bytes) -> str | None:
    """Identify an image from its magic bytes, or None if unrecognized.

    Hand-rolled rather than using a library: it's four formats, and the
    stdlib's imghdr (which would have covered this) was removed in Python
    3.13, which this app runs on.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    # WebP is a RIFF container: "RIFF" <4-byte length> "WEBP".
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def read_and_validate_upload(file: UploadFile) -> tuple[bytes, str]:
    """Read an uploaded image, enforcing the size cap and real file type.

    Returns (data, content_type) where content_type is the *sniffed* type,
    not whatever the client claimed. Raises 413 if too large, 400 if the
    bytes aren't a supported image.
    """
    # Read one byte past the limit: if we get it, the file is over the cap.
    # Reading exactly MAX_UPLOAD_BYTES couldn't tell "exactly at the limit"
    # apart from "larger and truncated".
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image must be {MAX_UPLOAD_BYTES // (1024 * 1024)} MB or smaller",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

    sniffed_type = sniff_image_type(data)
    if sniffed_type is None or sniffed_type not in ALLOWED_IMAGE_TYPES:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_TYPES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File must be one of: {allowed}",
        )
    return data, sniffed_type


def safe_media_type(stored_content_type: str | None) -> str:
    """The Content-Type to serve a stored image back with.

    Anything uploaded before the sniffing above existed has a
    client-supplied content_type in the database, which could still be
    something dangerous to render inline (e.g. a forged image/svg+xml).
    Falling back to octet-stream neutralizes those rows without needing a
    migration to re-check them.
    """
    if stored_content_type in ALLOWED_IMAGE_TYPES:
        return stored_content_type
    return "application/octet-stream"


def stream_and_release(minio_response):
    """Stream a MinIO object out, then always release its connection.

    The MinIO client holds an open HTTP connection until the response is
    closed *and* released, so both have to happen even if the client
    disconnects mid-download -- hence the finally.
    """
    try:
        yield from minio_response.stream(32 * 1024)
    finally:
        minio_response.close()
        minio_response.release_conn()
