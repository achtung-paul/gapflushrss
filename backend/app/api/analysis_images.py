# Plain photo gallery attached directly to an Analysis (as opposed to
# the Commodity's single annotated assembly image with markers -- see
# api/images.py). Any number of these per Analysis; no annotation
# involved, just upload/view/delete.

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.analyses import _get_analysis_or_404
from app.api.deps import get_current_user, get_project_db, get_project_minio_service, require_project_manager
from app.core import service_storage
from app.db.session import get_db
from app.models.analysis_image import AnalysisImage
from app.models.minio_service import MinioService
from app.models.user import User
from app.schemas.analysis_image import AnalysisImageOut

router = APIRouter(prefix="/projects/{project_id}", tags=["analysis-images"])


def _require_manager_for_analysis(
    db: Session, project_db: Session, user: User, project_id: int, analysis_id: int
) -> None:
    require_project_manager(db, user, project_id)
    _get_analysis_or_404(project_db, project_id, analysis_id)


def _get_analysis_image_or_404(project_db: Session, project_id: int, analysis_image_id: int) -> AnalysisImage:
    image = project_db.get(AnalysisImage, analysis_image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    _get_analysis_or_404(project_db, project_id, image.analysis_id)  # ownership check
    return image


@router.get("/analyses/{analysis_id}/images", response_model=list[AnalysisImageOut])
def list_analysis_images(
    project_id: int,
    analysis_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    _get_analysis_or_404(project_db, project_id, analysis_id)
    return (
        project_db.query(AnalysisImage)
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
    project_id: int,
    analysis_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    _require_manager_for_analysis(db, project_db, current_user, project_id, analysis_id)

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    data = await file.read()
    extension = Path(file.filename or "").suffix
    object_key = f"analyses/{analysis_id}/{uuid.uuid4()}{extension}"
    service_storage.upload_image(minio_service, object_key, data, file.content_type)

    image = AnalysisImage(
        analysis_id=analysis_id,
        object_key=object_key,
        original_filename=file.filename or object_key,
        content_type=file.content_type,
    )
    project_db.add(image)
    project_db.commit()
    project_db.refresh(image)
    return image


def _stream_and_release(minio_response):
    try:
        yield from minio_response.stream(32 * 1024)
    finally:
        minio_response.close()
        minio_response.release_conn()


@router.get("/analysis-images/{analysis_image_id}/file")
def get_analysis_image_file(
    project_id: int,
    analysis_image_id: int,
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    _: User = Depends(get_current_user),
):
    image = _get_analysis_image_or_404(project_db, project_id, analysis_image_id)
    minio_response = service_storage.get_image_stream(minio_service, image.object_key)
    return StreamingResponse(_stream_and_release(minio_response), media_type=image.content_type)


@router.delete("/analysis-images/{analysis_image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis_image(
    project_id: int,
    analysis_image_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
):
    image = _get_analysis_image_or_404(project_db, project_id, analysis_image_id)
    _require_manager_for_analysis(db, project_db, current_user, project_id, image.analysis_id)

    # MinIO never cascades at the DB level -- delete the object before
    # the row disappears, since object_key is the only record of where
    # the file lives (same gotcha as Commodity images, see api/images.py).
    service_storage.delete_image(minio_service, image.object_key)
    project_db.delete(image)
    project_db.commit()
