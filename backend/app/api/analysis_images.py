# Plain photo gallery attached directly to a Gap or Flush entry (as
# opposed to the Commodity's single annotated assembly image with
# markers -- see api/images.py). Any number of these per entry; no
# annotation involved, just upload/view/delete. Gap and Flush each get
# their own separate gallery, even though both hang off the same
# Analysis -- see models/analysis_image.py.

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.api.analyses import _get_entry_or_404
from app.api.deps import (
    get_current_user,
    get_project_db,
    get_project_minio_service,
    require_project_editor,
    require_project_manager,
)
from app.core import service_storage
from app.core.security_events import EVENT_DATA_DELETED, record_event
from app.core.uploads import (
    EXTENSION_BY_TYPE,
    read_and_validate_upload,
    safe_media_type,
    stream_and_release,
)
from app.db.session import get_db
from app.models.analysis_image import AnalysisImage, ImageTag
from app.models.minio_service import MinioService
from app.models.user import User
from app.schemas.analysis_image import AnalysisImageOut, AnalysisImageTagUpdate

router = APIRouter(prefix="/projects/{project_id}", tags=["analysis-images"])


# Sketch Agreed always sorts first, ahead of every other tag, regardless
# of upload order -- the rest fall back to upload order same as before
# tags existed. Shared by list_analysis_images below and api/exports.py's
# export_entry, so the gallery and the Excel export never disagree about
# which image leads.
def _tag_ordered(query):
    sketch_agreed_first = case((AnalysisImage.tag == ImageTag.sketch_agreed, 0), else_=1)
    return query.order_by(sketch_agreed_first, AnalysisImage.uploaded_at)


def _require_editor_for_entry(
    db: Session, project_db: Session, user: User, project_id: int, entry_id: int
) -> None:
    require_project_editor(db, user, project_id)
    _get_entry_or_404(project_db, project_id, entry_id)


def _require_manager_for_entry(
    db: Session, project_db: Session, user: User, project_id: int, entry_id: int
) -> None:
    require_project_manager(db, user, project_id)
    _get_entry_or_404(project_db, project_id, entry_id)


def _get_analysis_image_or_404(project_db: Session, project_id: int, analysis_image_id: int) -> AnalysisImage:
    image = project_db.get(AnalysisImage, analysis_image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    _get_entry_or_404(project_db, project_id, image.entry_id)  # ownership check
    return image


@router.get("/entries/{entry_id}/images", response_model=list[AnalysisImageOut])
def list_analysis_images(
    project_id: int,
    entry_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    _get_entry_or_404(project_db, project_id, entry_id)
    return _tag_ordered(project_db.query(AnalysisImage).filter(AnalysisImage.entry_id == entry_id)).all()


@router.post(
    "/entries/{entry_id}/images",
    response_model=AnalysisImageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_analysis_image(
    project_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    tag: ImageTag = Form(ImageTag.other),
):
    _require_editor_for_entry(db, project_db, current_user, project_id, entry_id)

    # content_type here is what the file actually is, not what the client
    # claimed -- see core/uploads.py.
    data, content_type = await read_and_validate_upload(file)
    object_key = f"entries/{entry_id}/{uuid.uuid4()}{EXTENSION_BY_TYPE[content_type]}"
    service_storage.upload_image(minio_service, object_key, data, content_type)

    image = AnalysisImage(
        entry_id=entry_id,
        object_key=object_key,
        original_filename=file.filename or object_key,
        content_type=content_type,
        tag=tag,
    )
    project_db.add(image)
    project_db.commit()
    project_db.refresh(image)
    return image


@router.patch("/analysis-images/{analysis_image_id}", response_model=AnalysisImageOut)
def update_analysis_image_tag(
    project_id: int,
    analysis_image_id: int,
    body: AnalysisImageTagUpdate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    # Tag-only edit, not a delete -- Manager-or-Contributor per
    # CLAUDE.md's editor/manager split, same rights as uploading.
    image = _get_analysis_image_or_404(project_db, project_id, analysis_image_id)
    _require_editor_for_entry(db, project_db, current_user, project_id, image.entry_id)

    image.tag = body.tag
    project_db.commit()
    project_db.refresh(image)
    return image


@router.get("/analysis-images/{analysis_image_id}/file")
def get_analysis_image_file(
    project_id: int,
    analysis_image_id: int,
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    _: User = Depends(get_current_user),
):
    # Deliberately not recorded to security_events -- same reasoning as
    # api/images.py's get_image_file: this is an <img src>, not a
    # deliberate download, and fires on every gallery render.
    image = _get_analysis_image_or_404(project_db, project_id, analysis_image_id)
    minio_response = service_storage.get_image_stream(minio_service, image.object_key)
    # Same nosniff / safe_media_type reasoning as api/images.py's
    # get_image_file.
    return StreamingResponse(
        stream_and_release(minio_response),
        media_type=safe_media_type(image.content_type),
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/analysis-images/{analysis_image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis_image(
    request: Request,
    project_id: int,
    analysis_image_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
):
    image = _get_analysis_image_or_404(project_db, project_id, analysis_image_id)
    _require_manager_for_entry(db, project_db, current_user, project_id, image.entry_id)
    image_name = image.original_filename

    # MinIO never cascades at the DB level -- delete the object before
    # the row disappears, since object_key is the only record of where
    # the file lives (same gotcha as Commodity images, see api/images.py).
    service_storage.delete_image(minio_service, image.object_key)
    project_db.delete(image)
    project_db.commit()

    # See api/chain_components.py's delete_chain_component for why this
    # is a separate commit on the central `db`.
    record_event(
        db,
        event_type=EVENT_DATA_DELETED,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="analysis_image",
        target_id=analysis_image_id,
        target_name=image_name,
    )
    db.commit()
