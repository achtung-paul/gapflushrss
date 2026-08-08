# Admin-editable reference data: process types, and the DIN
# 16742-style tolerance matrix (tolerance groups x dimension ranges,
# each cell holding an optional tool/non-tool +/- value). The brief's
# decision still applies: build the generic, editable structure now,
# load real DIN 16742/16901 figures into it later -- we don't invent
# values.
#
# Reading is open to any logged-in user (these lists feed dropdowns
# throughout the app, e.g. the Phase 5 tolerance chain builder). Writing
# is root_admin only -- this is system-wide config, not project-scoped,
# so there's no "project manager" equivalent here.

from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_root_admin
from app.core.tolerance_csv_import import MAX_IMPORT_BYTES, parse_tolerance_csv
from app.core.tolerance_csv_template import build_import_template
from app.db.session import get_db
from app.models.dimension_range import DimensionRange
from app.models.process_type import ProcessType
from app.models.tolerance_group import ToleranceGroup
from app.models.tolerance_value import ToleranceValue
from app.models.user import User
from app.schemas.reference_data import (
    DimensionRangeCreate,
    DimensionRangeOut,
    DimensionRangeUpdate,
    ProcessTypeCreate,
    ProcessTypeOut,
    ProcessTypeUpdate,
    ToleranceGroupCreate,
    ToleranceGroupOut,
    ToleranceGroupUpdate,
    ToleranceValueCellIn,
    ToleranceValueOut,
)

router = APIRouter(tags=["reference-data"])


def _get_process_type_or_404(db: Session, process_type_id: int) -> ProcessType:
    process_type = db.get(ProcessType, process_type_id)
    if process_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process type not found")
    return process_type


def _get_tolerance_group_or_404(db: Session, tolerance_group_id: int) -> ToleranceGroup:
    tolerance_group = db.get(ToleranceGroup, tolerance_group_id)
    if tolerance_group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tolerance group not found")
    return tolerance_group


def _get_dimension_range_or_404(db: Session, dimension_range_id: int) -> DimensionRange:
    dimension_range = db.get(DimensionRange, dimension_range_id)
    if dimension_range is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dimension range not found")
    return dimension_range


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


@router.get("/process-types/import-template")
def download_import_template(_: User = Depends(get_current_user)):
    # A read, not a write -- matches this router's split (any logged-in
    # user can read reference data, only root_admin can change it). The
    # template itself is instructional only, no real tolerance figures --
    # see core/tolerance_csv_template.py.
    content = build_import_template()
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="tolerance-import-template.xlsx"'},
    )


@router.post("/process-types/import", response_model=ProcessTypeOut, status_code=status.HTTP_201_CREATED)
async def import_process_type(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    """Create a brand-new process type and its whole tolerance matrix from
    one CSV upload -- see core/tolerance_csv_import.py for the expected
    format. Always creates a new process type; there is no merge/replace
    path here, since there's nothing to merge into yet.
    """
    name = name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name must not be blank")

    # Cheap check first -- no point parsing a large file just to fail on
    # a name collision (same 409 create_process_type already gives).
    existing = db.query(ProcessType).filter(ProcessType.name == name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Process type already exists")

    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a .csv file")

    # Read one byte past the limit, same pattern as core/uploads.py's
    # read_and_validate_upload -- getting that extra byte is how we know
    # the file was actually over the cap, not exactly at it.
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File must be {MAX_IMPORT_BYTES // (1024 * 1024)} MB or smaller",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

    try:
        text = data.decode("utf-8-sig")  # tolerate a BOM, which Excel's "CSV UTF-8" export adds
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be UTF-8 text")

    result = parse_tolerance_csv(text)
    if result.errors:
        # Same shape as Pydantic's own validation errors ({"msg": ...}
        # objects) -- client.js's errorMessage() already knows how to
        # join a list of those, so every problem in the file is surfaced
        # at once with no frontend changes needed.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"msg": error} for error in result.errors],
        )

    # Everything below is only reached once the whole file has validated
    # cleanly -- nothing is added to the session before this point, so a
    # rejected import creates nothing (get_db rolls back on close if an
    # exception were to happen here anyway).
    process_type = ProcessType(name=name)
    db.add(process_type)
    db.flush()  # assigns process_type.process_type_id

    dimension_ranges = [
        DimensionRange(
            process_type_id=process_type.process_type_id,
            sequence_number=sequence_number,
            min_value=parsed_range.min_value,
            max_value=parsed_range.max_value,
        )
        for sequence_number, parsed_range in enumerate(result.ranges, start=1)
    ]
    db.add_all(dimension_ranges)
    db.flush()  # assigns each dimension_range_id

    tolerance_groups = [
        ToleranceGroup(
            process_type_id=process_type.process_type_id,
            sequence_number=sequence_number,
            name=parsed_group.name,
        )
        for sequence_number, parsed_group in enumerate(result.groups, start=1)
    ]
    db.add_all(tolerance_groups)
    db.flush()  # assigns each tolerance_group_id

    # Zip is safe here: tolerance_groups was built by enumerating
    # result.groups in the same order, one-to-one.
    for tolerance_group, parsed_group in zip(tolerance_groups, result.groups):
        cell_positions = set(parsed_group.tool_values) | set(parsed_group.non_tool_values)
        for range_position in cell_positions:
            db.add(
                ToleranceValue(
                    tolerance_group_id=tolerance_group.tolerance_group_id,
                    dimension_range_id=dimension_ranges[range_position].dimension_range_id,
                    tool_value=parsed_group.tool_values.get(range_position),
                    non_tool_value=parsed_group.non_tool_values.get(range_position),
                )
            )

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
    db.delete(process_type)  # cascades to its tolerance groups/ranges (ondelete="CASCADE")
    db.commit()


@router.get(
    "/process-types/{process_type_id}/tolerance-groups",
    response_model=list[ToleranceGroupOut],
)
def list_tolerance_groups(
    process_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_process_type_or_404(db, process_type_id)
    return (
        db.query(ToleranceGroup)
        .filter(ToleranceGroup.process_type_id == process_type_id)
        .order_by(ToleranceGroup.sequence_number)
        .all()
    )


@router.post(
    "/process-types/{process_type_id}/tolerance-groups",
    response_model=ToleranceGroupOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tolerance_group(
    process_type_id: int,
    body: ToleranceGroupCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    _get_process_type_or_404(db, process_type_id)

    highest_sequence = (
        db.query(func.max(ToleranceGroup.sequence_number))
        .filter(ToleranceGroup.process_type_id == process_type_id)
        .scalar()
    )
    tolerance_group = ToleranceGroup(
        process_type_id=process_type_id,
        sequence_number=(highest_sequence or 0) + 1,
        name=body.name,
    )
    db.add(tolerance_group)
    db.commit()
    db.refresh(tolerance_group)
    return tolerance_group


@router.put("/tolerance-groups/{tolerance_group_id}", response_model=ToleranceGroupOut)
def update_tolerance_group(
    tolerance_group_id: int,
    body: ToleranceGroupUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    tolerance_group = _get_tolerance_group_or_404(db, tolerance_group_id)
    tolerance_group.name = body.name
    db.commit()
    db.refresh(tolerance_group)
    return tolerance_group


@router.delete("/tolerance-groups/{tolerance_group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tolerance_group(
    tolerance_group_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    tolerance_group = _get_tolerance_group_or_404(db, tolerance_group_id)
    db.delete(tolerance_group)  # cascades to its matrix cells (ondelete="CASCADE")
    db.commit()


@router.get(
    "/process-types/{process_type_id}/dimension-ranges",
    response_model=list[DimensionRangeOut],
)
def list_dimension_ranges(
    process_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_process_type_or_404(db, process_type_id)
    return (
        db.query(DimensionRange)
        .filter(DimensionRange.process_type_id == process_type_id)
        .order_by(DimensionRange.sequence_number)
        .all()
    )


@router.post(
    "/process-types/{process_type_id}/dimension-ranges",
    response_model=DimensionRangeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_dimension_range(
    process_type_id: int,
    body: DimensionRangeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    _get_process_type_or_404(db, process_type_id)

    highest_sequence = (
        db.query(func.max(DimensionRange.sequence_number))
        .filter(DimensionRange.process_type_id == process_type_id)
        .scalar()
    )
    dimension_range = DimensionRange(
        process_type_id=process_type_id,
        sequence_number=(highest_sequence or 0) + 1,
        min_value=body.min_value,
        max_value=body.max_value,
    )
    db.add(dimension_range)
    db.commit()
    db.refresh(dimension_range)
    return dimension_range


@router.put("/dimension-ranges/{dimension_range_id}", response_model=DimensionRangeOut)
def update_dimension_range(
    dimension_range_id: int,
    body: DimensionRangeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    dimension_range = _get_dimension_range_or_404(db, dimension_range_id)
    dimension_range.min_value = body.min_value
    dimension_range.max_value = body.max_value
    db.commit()
    db.refresh(dimension_range)
    return dimension_range


@router.delete("/dimension-ranges/{dimension_range_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dimension_range(
    dimension_range_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    dimension_range = _get_dimension_range_or_404(db, dimension_range_id)
    db.delete(dimension_range)  # cascades to its matrix cells (ondelete="CASCADE")
    db.commit()


@router.get(
    "/process-types/{process_type_id}/tolerance-values",
    response_model=list[ToleranceValueOut],
)
def list_tolerance_values(
    process_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Flat list of every populated cell for this process type's matrix
    # -- the frontend cross-references this against its group/range
    # lists (by id) to lay the matrix out. A cell with no row here is a
    # blank "-" cell.
    _get_process_type_or_404(db, process_type_id)
    return (
        db.query(ToleranceValue)
        .join(ToleranceGroup, ToleranceValue.tolerance_group_id == ToleranceGroup.tolerance_group_id)
        .filter(ToleranceGroup.process_type_id == process_type_id)
        .all()
    )


@router.put(
    "/tolerance-groups/{tolerance_group_id}/dimension-ranges/{dimension_range_id}/value",
    response_model=ToleranceValueOut | None,
)
def set_tolerance_value_cell(
    tolerance_group_id: int,
    dimension_range_id: int,
    body: ToleranceValueCellIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
):
    _get_tolerance_group_or_404(db, tolerance_group_id)
    _get_dimension_range_or_404(db, dimension_range_id)

    cell = (
        db.query(ToleranceValue)
        .filter_by(tolerance_group_id=tolerance_group_id, dimension_range_id=dimension_range_id)
        .first()
    )

    if body.tool_value is None and body.non_tool_value is None:
        # Both cleared -- go back to "no row", the standard's blank "-"
        # cell, rather than storing an empty row.
        if cell is not None:
            db.delete(cell)
            db.commit()
        return None

    if cell is None:
        cell = ToleranceValue(
            tolerance_group_id=tolerance_group_id, dimension_range_id=dimension_range_id
        )
        db.add(cell)

    cell.tool_value = body.tool_value
    cell.non_tool_value = body.non_tool_value
    db.commit()
    db.refresh(cell)
    return cell
