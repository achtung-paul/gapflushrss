# Image upload/serving for an Analysis, and the numbered markers placed
# on those images (brief step 2: image annotation).
#
# Files themselves live in MinIO (see core/storage.py); this router only
# ever proxies bytes through the backend rather than exposing MinIO
# directly to the browser, and stores/reads position metadata in Postgres.

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.analyses import _get_analysis_or_404, _get_commodity_or_404
from app.api.deps import get_current_user, require_project_manager
from app.core.storage import delete_image, get_image_stream, upload_image
from app.db.session import get_db
from app.models.image import Image
from app.models.marker import Marker
from app.models.user import User
from app.schemas.image import ImageOut
from app.schemas.marker import MarkerCreate, MarkerOut

router = APIRouter(tags=["images"])


def _require_manager_for_analysis(db: Session, user: User, analysis_id: int) -> None:
    analysis = _get_analysis_or_404(db, analysis_id)
    commodity = _get_commodity_or_404(db, analysis.commodity_id)
    require_project_manager(db, user, commodity.project_id)


def _get_image_or_404(db: Session, image_id: int) -> Image:
    image = db.get(Image, image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return image


@router.get("/analyses/{analysis_id}/images", response_model=list[ImageOut])
def list_images(
    analysis_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Image).filter(Image.analysis_id == analysis_id).order_by(Image.uploaded_at).all()


@router.post(
    "/analyses/{analysis_id}/images",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_analysis_image(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    _require_manager_for_analysis(db, current_user, analysis_id)

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    data = await file.read()
    extension = Path(file.filename or "").suffix
    object_key = f"analyses/{analysis_id}/{uuid.uuid4()}{extension}"
    upload_image(object_key, data, file.content_type)

    image = Image(
        analysis_id=analysis_id,
        object_key=object_key,
        original_filename=file.filename or object_key,
        content_type=file.content_type,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def _stream_and_release(minio_response):
    try:
        yield from minio_response.stream(32 * 1024)
    finally:
        minio_response.close()
        minio_response.release_conn()


@router.get("/images/{image_id}/file")
def get_image_file(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    image = _get_image_or_404(db, image_id)
    minio_response = get_image_stream(image.object_key)
    return StreamingResponse(_stream_and_release(minio_response), media_type=image.content_type)


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image = _get_image_or_404(db, image_id)
    _require_manager_for_analysis(db, current_user, image.analysis_id)

    delete_image(image.object_key)
    db.delete(image)  # cascades to its markers (ondelete="CASCADE")
    db.commit()


@router.get("/images/{image_id}/markers", response_model=list[MarkerOut])
def list_markers(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_image_or_404(db, image_id)
    return db.query(Marker).filter(Marker.image_id == image_id).order_by(Marker.sequence_number).all()


@router.post("/images/{image_id}/markers", response_model=MarkerOut, status_code=status.HTTP_201_CREATED)
def create_marker(
    image_id: int,
    body: MarkerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image = _get_image_or_404(db, image_id)
    _require_manager_for_analysis(db, current_user, image.analysis_id)

    highest_sequence = (
        db.query(func.max(Marker.sequence_number)).filter(Marker.image_id == image_id).scalar()
    )
    next_sequence = (highest_sequence or 0) + 1

    marker = Marker(image_id=image_id, sequence_number=next_sequence, x=body.x, y=body.y)
    db.add(marker)
    db.commit()
    db.refresh(marker)
    return marker


@router.delete("/markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marker(
    marker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    marker = db.get(Marker, marker_id)
    if marker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marker not found")

    image = _get_image_or_404(db, marker.image_id)
    _require_manager_for_analysis(db, current_user, image.analysis_id)

    db.delete(marker)
    db.commit()
