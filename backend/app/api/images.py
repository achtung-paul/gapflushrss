# Image upload/serving for a Commodity's shared assembly photo, and the
# numbered markers placed on it (brief step 2: image annotation). Each
# marker IS an Analysis -- creating one atomically creates its Analysis
# row (see create_marker), and deleting one deletes that Analysis and
# everything under it (see delete_marker).
#
# Files themselves live in MinIO (see core/storage.py); this router only
# ever proxies bytes through the backend rather than exposing MinIO
# directly to the browser, and stores/reads position metadata in Postgres.

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.analyses import _get_analysis_or_404, _get_commodity_or_404, next_analysis_sequence_number
from app.api.deps import get_current_user, require_project_manager
from app.core.storage import delete_image, get_image_stream, upload_image
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.commodity import Commodity
from app.models.image import Image
from app.models.marker import Marker
from app.models.user import User
from app.schemas.image import ImageOut
from app.schemas.marker import MarkerCreate, MarkerOut

router = APIRouter(tags=["images"])


def _require_manager_for_commodity(db: Session, user: User, commodity_id: int) -> None:
    commodity = _get_commodity_or_404(db, commodity_id)
    require_project_manager(db, user, commodity.project_id)


def _get_image_or_404(db: Session, image_id: int) -> Image:
    image = db.get(Image, image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return image


def _marker_out(marker: Marker, analysis: Analysis) -> MarkerOut:
    return MarkerOut(
        marker_id=marker.marker_id,
        image_id=marker.image_id,
        analysis_id=analysis.analysis_id,
        analysis_code=analysis.analysis_code,
        sequence_number=analysis.sequence_number,
        x=marker.x,
        y=marker.y,
    )


@router.get("/commodities/{commodity_id}/images", response_model=list[ImageOut])
def list_images(
    commodity_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Image).filter(Image.commodity_id == commodity_id).order_by(Image.uploaded_at).all()


@router.post(
    "/commodities/{commodity_id}/images",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_commodity_image(
    commodity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    _require_manager_for_commodity(db, current_user, commodity_id)

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    data = await file.read()
    extension = Path(file.filename or "").suffix
    object_key = f"commodities/{commodity_id}/{uuid.uuid4()}{extension}"
    upload_image(object_key, data, file.content_type)

    image = Image(
        commodity_id=commodity_id,
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
def delete_commodity_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image = _get_image_or_404(db, image_id)
    _require_manager_for_commodity(db, current_user, image.commodity_id)

    delete_image(image.object_key)
    # Cascades to its markers (ondelete="CASCADE"), but NOT to the
    # Analyses those markers pointed at -- removing a photo shouldn't
    # wipe out Gap/Flush data. Those analyses just lose their marker and
    # become placeholders again, still reachable from the plain list.
    db.delete(image)
    db.commit()


@router.get("/images/{image_id}/markers", response_model=list[MarkerOut])
def list_markers(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_image_or_404(db, image_id)
    rows = (
        db.query(Marker, Analysis)
        .join(Analysis, Marker.analysis_id == Analysis.analysis_id)
        .filter(Marker.image_id == image_id)
        .order_by(Analysis.sequence_number)
        .all()
    )
    return [_marker_out(marker, analysis) for marker, analysis in rows]


@router.post("/images/{image_id}/markers", response_model=MarkerOut, status_code=status.HTTP_201_CREATED)
def create_marker(
    image_id: int,
    body: MarkerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image = _get_image_or_404(db, image_id)
    _require_manager_for_commodity(db, current_user, image.commodity_id)
    commodity = db.get(Commodity, image.commodity_id)

    next_sequence = next_analysis_sequence_number(db, commodity.commodity_id)
    analysis = Analysis(
        commodity_id=commodity.commodity_id,
        sequence_number=next_sequence,
        analysis_code=f"{commodity.code}-{next_sequence:03d}",
    )
    db.add(analysis)
    db.flush()  # assigns analysis.analysis_id without ending the transaction

    marker = Marker(image_id=image_id, analysis_id=analysis.analysis_id, x=body.x, y=body.y)
    db.add(marker)
    db.commit()
    db.refresh(marker)
    db.refresh(analysis)
    return _marker_out(marker, analysis)


@router.delete("/markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marker(
    marker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    marker = db.get(Marker, marker_id)
    if marker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marker not found")

    analysis = _get_analysis_or_404(db, marker.analysis_id)
    _require_manager_for_commodity(db, current_user, analysis.commodity_id)

    # Deletes the marker (ondelete="CASCADE") along with everything else
    # under the analysis (AnalysisEntry -> ChainComponent). Images are
    # untouched -- only the marker/analysis pair is removed.
    db.delete(analysis)
    db.commit()
