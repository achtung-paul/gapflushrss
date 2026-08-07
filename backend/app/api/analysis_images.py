# Plain photo gallery attached directly to an Analysis (as opposed to
# the Commodity's single annotated assembly image with markers -- see
# api/images.py). Any number of these per Analysis; no annotation
# involved, just upload/view/delete.

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.analyses import _get_analysis_or_404, _get_commodity_or_404
from app.api.deps import get_current_user, require_project_manager
from app.core.storage import delete_image, get_image_stream, upload_image
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.analysis_image import AnalysisImage
from app.models.user import User
from app.schemas.analysis_image import AnalysisImageOut

router = APIRouter(tags=["analysis-images"])


def _require_manager_for_analysis(db: Session, user: User, analysis: Analysis) -> None:
    commodity = _get_commodity_or_404(db, analysis.commodity_id)
    require_project_manager(db, user, commodity.project_id)


def _get_analysis_image_or_404(db: Session, analysis_image_id: int) -> AnalysisImage:
    image = db.get(AnalysisImage, analysis_image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return image


@router.get("/analyses/{analysis_id}/images", response_model=list[AnalysisImageOut])
def list_analysis_images(
    analysis_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_analysis_or_404(db, analysis_id)
    return (
        db.query(AnalysisImage)
        .filter(AnalysisImage.analysis_id == analysis_id)
        .order_by(AnalysisImage.uploaded_at)
        .all()
    )


@router.post(
    "/analyses/{analysis_id}/images",
    response_model=AnalysisImageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_analysis_image(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    analysis = _get_analysis_or_404(db, analysis_id)
    _require_manager_for_analysis(db, current_user, analysis)

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    data = await file.read()
    extension = Path(file.filename or "").suffix
    object_key = f"analyses/{analysis_id}/{uuid.uuid4()}{extension}"
    upload_image(object_key, data, file.content_type)

    image = AnalysisImage(
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


@router.get("/analysis-images/{analysis_image_id}/file")
def get_analysis_image_file(
    analysis_image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    image = _get_analysis_image_or_404(db, analysis_image_id)
    minio_response = get_image_stream(image.object_key)
    return StreamingResponse(_stream_and_release(minio_response), media_type=image.content_type)


@router.delete("/analysis-images/{analysis_image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis_image(
    analysis_image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image = _get_analysis_image_or_404(db, analysis_image_id)
    analysis = _get_analysis_or_404(db, image.analysis_id)
    _require_manager_for_analysis(db, current_user, analysis)

    # MinIO never cascades at the DB level -- delete the object before
    # the row disappears, since object_key is the only record of where
    # the file lives (same gotcha as Commodity images, see api/images.py).
    delete_image(image.object_key)
    db.delete(image)
    db.commit()
