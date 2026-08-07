# Image upload/serving for a Commodity's shared assembly photo, and the
# numbered markers placed on it (brief step 2: image annotation). Each
# marker IS an Analysis -- creating one atomically creates its Analysis
# row (see create_marker), and deleting one deletes that Analysis and
# everything under it (see delete_marker).
#
# Files themselves live in MinIO, on whichever MinioService this
# project is assigned to (see core/service_storage.py); this router only
# ever proxies bytes through the backend rather than exposing MinIO
# directly to the browser, and stores/reads position metadata in Postgres.

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.analyses import _get_analysis_or_404, _get_commodity_or_404, next_analysis_sequence_number
from app.api.deps import get_current_user, get_project_db, get_project_minio_service, require_project_manager
from app.core import service_storage
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.commodity import Commodity
from app.models.image import Image
from app.models.marker import Marker
from app.models.minio_service import MinioService
from app.models.user import User
from app.schemas.image import ImageOut
from app.schemas.marker import MarkerCreate, MarkerOut, Point

router = APIRouter(prefix="/projects/{project_id}", tags=["images"])


def _require_manager_for_commodity(
    db: Session, project_db: Session, user: User, project_id: int, commodity_id: int
) -> None:
    require_project_manager(db, user, project_id)
    _get_commodity_or_404(project_db, project_id, commodity_id)


def _get_image_or_404(project_db: Session, project_id: int, image_id: int) -> Image:
    image = project_db.get(Image, image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    _get_commodity_or_404(project_db, project_id, image.commodity_id)  # ownership check
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
        points=[Point(x=p[0], y=p[1]) for p in marker.points],
    )


@router.get("/commodities/{commodity_id}/images", response_model=list[ImageOut])
def list_images(
    project_id: int,
    commodity_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    _get_commodity_or_404(project_db, project_id, commodity_id)
    return (
        project_db.query(Image)
        .filter(Image.commodity_id == commodity_id)
        .order_by(Image.uploaded_at)
        .all()
    )


@router.post(
    "/commodities/{commodity_id}/images",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_commodity_image(
    project_id: int,
    commodity_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    _require_manager_for_commodity(db, project_db, current_user, project_id, commodity_id)

    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be an image")

    data = await file.read()
    extension = Path(file.filename or "").suffix
    object_key = f"commodities/{commodity_id}/{uuid.uuid4()}{extension}"
    service_storage.upload_image(minio_service, object_key, data, file.content_type)

    image = Image(
        commodity_id=commodity_id,
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


@router.get("/images/{image_id}/file")
def get_image_file(
    project_id: int,
    image_id: int,
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    _: User = Depends(get_current_user),
):
    image = _get_image_or_404(project_db, project_id, image_id)
    minio_response = service_storage.get_image_stream(minio_service, image.object_key)
    return StreamingResponse(_stream_and_release(minio_response), media_type=image.content_type)


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_commodity_image(
    project_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
):
    image = _get_image_or_404(project_db, project_id, image_id)
    _require_manager_for_commodity(db, project_db, current_user, project_id, image.commodity_id)

    service_storage.delete_image(minio_service, image.object_key)
    # Cascades to its markers (ondelete="CASCADE"), but NOT to the
    # Analyses those markers pointed at -- removing a photo shouldn't
    # wipe out Gap/Flush data. Those analyses just lose their marker and
    # become placeholders again, still reachable from the plain list.
    project_db.delete(image)
    project_db.commit()


@router.get("/images/{image_id}/markers", response_model=list[MarkerOut])
def list_markers(
    project_id: int,
    image_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    _get_image_or_404(project_db, project_id, image_id)
    rows = (
        project_db.query(Marker, Analysis)
        .join(Analysis, Marker.analysis_id == Analysis.analysis_id)
        .filter(Marker.image_id == image_id)
        .order_by(Analysis.sequence_number)
        .all()
    )
    return [_marker_out(marker, analysis) for marker, analysis in rows]


@router.post("/images/{image_id}/markers", response_model=MarkerOut, status_code=status.HTTP_201_CREATED)
def create_marker(
    project_id: int,
    image_id: int,
    body: MarkerCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    image = _get_image_or_404(project_db, project_id, image_id)
    _require_manager_for_commodity(db, project_db, current_user, project_id, image.commodity_id)
    commodity = project_db.get(Commodity, image.commodity_id)

    next_sequence = next_analysis_sequence_number(project_db, commodity.commodity_id)
    analysis = Analysis(
        commodity_id=commodity.commodity_id,
        sequence_number=next_sequence,
        analysis_code=f"{commodity.code}-{next_sequence:03d}",
    )
    project_db.add(analysis)
    project_db.flush()  # assigns analysis.analysis_id without ending the transaction

    # The marker balloon sits at the polyline's last point.
    endpoint = body.points[-1]
    marker = Marker(
        image_id=image_id,
        analysis_id=analysis.analysis_id,
        x=endpoint.x,
        y=endpoint.y,
        points=[[p.x, p.y] for p in body.points],
    )
    project_db.add(marker)
    project_db.commit()
    project_db.refresh(marker)
    project_db.refresh(analysis)
    return _marker_out(marker, analysis)


@router.delete("/markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marker(
    project_id: int,
    marker_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    marker = project_db.get(Marker, marker_id)
    if marker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marker not found")

    analysis = _get_analysis_or_404(project_db, project_id, marker.analysis_id)
    _require_manager_for_commodity(db, project_db, current_user, project_id, analysis.commodity_id)

    # Deletes the marker (ondelete="CASCADE") along with everything else
    # under the analysis (AnalysisEntry -> ChainComponent). Images are
    # untouched -- only the marker/analysis pair is removed.
    project_db.delete(analysis)
    project_db.commit()
