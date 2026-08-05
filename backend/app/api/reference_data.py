# Admin-editable reference data: process types, and the generic
# "process type -> tolerance class -> value" table (brief: build this
# generically now, load real DIN 16742/16901 figures into it later).
#
# Reading is open to any logged-in user (these lists feed dropdowns
# throughout the app, e.g. the Phase 5 tolerance chain builder). Writing
# is root_admin only -- this is system-wide config, not project-scoped,
# so there's no "project manager" equivalent here.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_root_admin
from app.db.session import get_db
from app.models.process_type import ProcessType
from app.models.tolerance_class import ToleranceClass
from app.models.user import User
from app.schemas.reference_data import (
    ProcessTypeCreate,
    ProcessTypeOut,
    ProcessTypeUpdate,
    ToleranceClassCreate,
    ToleranceClassOut,
    ToleranceClassUpdate,
)

router = APIRouter(tags=["reference-data"])


def _get_process_type_or_404(db: Session, process_type_id: int) -> ProcessType:
    process_type = db.get(ProcessType, process_type_id)
    if process_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process type not found")
    return process_type


@router.get("/process-types", response_model=list[ProcessTypeOut])
def list_process_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(ProcessType).order_by(ProcessType.name).all()


@router.post("/process-types", response_model=ProcessTypeOut, status_code=status.HTTP_201_CREATED)
def create_process_type(
    body: ProcessTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    existing = db.query(ProcessType).filter(ProcessType.name == body.name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Process type already exists")

    process_type = ProcessType(name=body.name)
    db.add(process_type)
    db.commit()
    db.refresh(process_type)
    return process_type


@router.put("/process-types/{process_type_id}", response_model=ProcessTypeOut)
def update_process_type(
    process_type_id: int,
    body: ProcessTypeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    process_type = _get_process_type_or_404(db, process_type_id)
    process_type.name = body.name
    db.commit()
    db.refresh(process_type)
    return process_type


@router.delete("/process-types/{process_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_process_type(
    process_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    process_type = _get_process_type_or_404(db, process_type_id)
    db.delete(process_type)  # cascades to its tolerance classes (ondelete="CASCADE")
    db.commit()


@router.get(
    "/process-types/{process_type_id}/tolerance-classes",
    response_model=list[ToleranceClassOut],
)
def list_tolerance_classes(
    process_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_process_type_or_404(db, process_type_id)
    return (
        db.query(ToleranceClass)
        .filter(ToleranceClass.process_type_id == process_type_id)
        .order_by(ToleranceClass.class_name)
        .all()
    )


@router.post(
    "/process-types/{process_type_id}/tolerance-classes",
    response_model=ToleranceClassOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tolerance_class(
    process_type_id: int,
    body: ToleranceClassCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    _get_process_type_or_404(db, process_type_id)

    existing = (
        db.query(ToleranceClass)
        .filter_by(process_type_id=process_type_id, class_name=body.class_name)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tolerance class already exists for this process type",
        )

    tolerance_class = ToleranceClass(
        process_type_id=process_type_id, class_name=body.class_name, value=body.value
    )
    db.add(tolerance_class)
    db.commit()
    db.refresh(tolerance_class)
    return tolerance_class


@router.put("/tolerance-classes/{tolerance_class_id}", response_model=ToleranceClassOut)
def update_tolerance_class(
    tolerance_class_id: int,
    body: ToleranceClassUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    tolerance_class = db.get(ToleranceClass, tolerance_class_id)
    if tolerance_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tolerance class not found")

    tolerance_class.class_name = body.class_name
    tolerance_class.value = body.value
    db.commit()
    db.refresh(tolerance_class)
    return tolerance_class


@router.delete("/tolerance-classes/{tolerance_class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tolerance_class(
    tolerance_class_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    tolerance_class = db.get(ToleranceClass, tolerance_class_id)
    if tolerance_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tolerance class not found")

    db.delete(tolerance_class)
    db.commit()
