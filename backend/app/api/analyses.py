# Analyses live under a Commodity, and each gets an auto-generated unique
# ID (commodity code + zero-padded sequence number, e.g. "DR-001"). A Gap
# and/or Flush entry can then be attached to an Analysis -- at least one
# is expected eventually, but the brief explicitly allows an Analysis to
# exist as a placeholder with neither yet.
#
# There's no POST route here to create one directly -- an Analysis only
# ever comes into being as the side effect of dropping a marker on the
# commodity's assembly image (see api/images.py's create_marker), which
# is why next_analysis_sequence_number is exposed as a module-level
# function rather than kept private to a route handler.
#
# Every route here takes both `db` (central -- permission checks only)
# and `project_db` (the actual Commodity-and-below data, on whichever
# Postgres service this project is assigned to -- see api/deps.py's
# get_project_db). The _get_X_or_404 helpers below are imported by
# chain_components.py, images.py, and analysis_images.py too.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_project_db, require_project_editor, require_project_manager
from app.core import service_storage
from app.core.html_sanitize import sanitize_notes
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.analysis_entry import AnalysisEntry, EntryType
from app.models.analysis_image import AnalysisImage
from app.models.commodity import Commodity
from app.models.user import User
from app.schemas.analysis import AnalysisDetailOut, AnalysisUpdate
from app.schemas.analysis_entry import AnalysisEntryCreate, AnalysisEntryOut, AngledSettingsUpdate

router = APIRouter(prefix="/projects/{project_id}", tags=["analyses"])


def _get_commodity_or_404(project_db: Session, project_id: int, commodity_id: int) -> Commodity:
    commodity = project_db.get(Commodity, commodity_id)
    if commodity is None or commodity.project_id != project_id:
        # project_id is a plain column now, not a real FK (see
        # models/commodity.py) -- projects colocated on the same
        # Postgres service share this table, so existence alone isn't
        # enough; every fetch has to check ownership too.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commodity not found")
    return commodity


def _get_analysis_or_404(project_db: Session, project_id: int, analysis_id: int) -> Analysis:
    analysis = project_db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    _get_commodity_or_404(project_db, project_id, analysis.commodity_id)  # ownership check
    return analysis


def _get_entry_or_404(project_db: Session, project_id: int, entry_id: int) -> AnalysisEntry:
    entry = project_db.get(AnalysisEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    _get_analysis_or_404(project_db, project_id, entry.analysis_id)  # ownership check
    return entry


def _entry_out(analysis: Analysis, entry: AnalysisEntry) -> AnalysisEntryOut:
    return AnalysisEntryOut(
        entry_id=entry.entry_id,
        analysis_id=entry.analysis_id,
        entry_type=entry.entry_type,
        entry_code=f"{analysis.analysis_code}-{entry.entry_type.value}",
        nominal_value=entry.nominal_value,
        upper_limit=entry.upper_limit,
        lower_limit=entry.lower_limit,
        direction=entry.direction,
        created_by_name=entry.created_by_name,
        updated_by_name=entry.updated_by_name,
        notes=entry.notes,
        interface_angle=entry.interface_angle,
        calculation_method=entry.calculation_method,
    )


def delete_analysis_images_from_storage(
    project_db: Session, minio_service, analysis_ids: list[int]
) -> None:
    """Remove the MinIO objects for every AnalysisImage under these analyses.

    Must be called *before* the analyses (or their entries, or the images
    themselves) are deleted from the database. AnalysisImage.entry_id
    cascades on delete (through AnalysisEntry.analysis_id, which itself
    cascades from Analysis), so dropping an Analysis silently takes its
    image rows with it -- and `object_key` is the only record of where
    each file actually lives, so once those rows are gone the objects can
    never be found again. MinIO has no knowledge of the database and
    cascades nothing.

    Shared by api/images.py's delete_marker and api/projects.py's
    delete_project so this only has to be right in one place -- it was
    originally missed in delete_marker.
    """
    if not analysis_ids:
        return

    # AnalysisImage no longer references Analysis directly (see
    # models/analysis_image.py) -- go via whichever Gap/Flush entries
    # these analyses have.
    entry_ids = [
        row[0]
        for row in project_db.query(AnalysisEntry.entry_id)
        .filter(AnalysisEntry.analysis_id.in_(analysis_ids))
        .all()
    ]
    if not entry_ids:
        return

    analysis_images = (
        project_db.query(AnalysisImage).filter(AnalysisImage.entry_id.in_(entry_ids)).all()
    )
    for analysis_image in analysis_images:
        service_storage.delete_image(minio_service, analysis_image.object_key)


def next_analysis_sequence_number(project_db: Session, commodity_id: int) -> int:
    highest_sequence = (
        project_db.query(func.max(Analysis.sequence_number))
        .filter(Analysis.commodity_id == commodity_id)
        .scalar()
    )
    return (highest_sequence or 0) + 1


def _analysis_detail_out(project_db: Session, analysis: Analysis) -> AnalysisDetailOut:
    entries = (
        project_db.query(AnalysisEntry).filter(AnalysisEntry.analysis_id == analysis.analysis_id).all()
    )
    gap = next((e for e in entries if e.entry_type == EntryType.GAP), None)
    flush = next((e for e in entries if e.entry_type == EntryType.FLUSH), None)

    return AnalysisDetailOut(
        analysis_id=analysis.analysis_id,
        commodity_id=analysis.commodity_id,
        analysis_code=analysis.analysis_code,
        sequence_number=analysis.sequence_number,
        description=analysis.description,
        gap=_entry_out(analysis, gap) if gap else None,
        flush=_entry_out(analysis, flush) if flush else None,
    )


@router.get("/commodities/{commodity_id}/analyses", response_model=list[AnalysisDetailOut])
def list_analyses(
    project_id: int,
    commodity_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    _get_commodity_or_404(project_db, project_id, commodity_id)
    analyses = (
        project_db.query(Analysis)
        .filter(Analysis.commodity_id == commodity_id)
        .order_by(Analysis.sequence_number)
        .all()
    )
    return [_analysis_detail_out(project_db, analysis) for analysis in analyses]


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetailOut)
def get_analysis(
    project_id: int,
    analysis_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    analysis = _get_analysis_or_404(project_db, project_id, analysis_id)
    return _analysis_detail_out(project_db, analysis)


@router.put("/analyses/{analysis_id}", response_model=AnalysisDetailOut)
def update_analysis(
    project_id: int,
    analysis_id: int,
    body: AnalysisUpdate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    require_project_editor(db, current_user, project_id)
    analysis = _get_analysis_or_404(project_db, project_id, analysis_id)
    analysis.description = body.description
    project_db.commit()
    return _analysis_detail_out(project_db, analysis)


def _create_entry(
    project_id: int,
    analysis_id: int,
    entry_type: EntryType,
    body: AnalysisEntryCreate,
    db: Session,
    project_db: Session,
    current_user: User,
) -> AnalysisEntryOut:
    require_project_editor(db, current_user, project_id)
    analysis = _get_analysis_or_404(project_db, project_id, analysis_id)

    already_exists = (
        project_db.query(AnalysisEntry)
        .filter_by(analysis_id=analysis_id, entry_type=entry_type)
        .first()
    )
    if already_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{entry_type.value} already attached to this analysis",
        )

    actor_name = f"{current_user.first_name} {current_user.last_name}"
    entry = AnalysisEntry(
        analysis_id=analysis_id,
        entry_type=entry_type,
        nominal_value=body.nominal_value,
        upper_limit=body.upper_limit,
        lower_limit=body.lower_limit,
        direction=body.direction,
        created_by_name=actor_name,
        updated_by_name=actor_name,
        # Sanitised on the way in, never on the way out -- see
        # core/html_sanitize.py.
        notes=sanitize_notes(body.notes),
    )
    project_db.add(entry)
    project_db.commit()
    project_db.refresh(entry)
    return _entry_out(analysis, entry)


@router.post(
    "/analyses/{analysis_id}/gap",
    response_model=AnalysisEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_gap_entry(
    project_id: int,
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    return _create_entry(project_id, analysis_id, EntryType.GAP, body, db, project_db, current_user)


@router.post(
    "/analyses/{analysis_id}/flush",
    response_model=AnalysisEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_flush_entry(
    project_id: int,
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    return _create_entry(project_id, analysis_id, EntryType.FLUSH, body, db, project_db, current_user)


def _update_entry(
    project_id: int,
    analysis_id: int,
    entry_type: EntryType,
    body: AnalysisEntryCreate,
    db: Session,
    project_db: Session,
    current_user: User,
) -> AnalysisEntryOut:
    require_project_editor(db, current_user, project_id)
    analysis = _get_analysis_or_404(project_db, project_id, analysis_id)

    entry = project_db.query(AnalysisEntry).filter_by(analysis_id=analysis_id, entry_type=entry_type).first()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entry_type.value} not attached to this analysis yet",
        )

    entry.nominal_value = body.nominal_value
    entry.upper_limit = body.upper_limit
    entry.lower_limit = body.lower_limit
    entry.direction = body.direction
    entry.notes = sanitize_notes(body.notes)
    entry.updated_by_name = f"{current_user.first_name} {current_user.last_name}"
    project_db.commit()
    project_db.refresh(entry)
    return _entry_out(analysis, entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    project_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    entry = _get_entry_or_404(project_db, project_id, entry_id)
    require_project_manager(db, current_user, project_id)

    # Cascades to its chain components (ondelete="CASCADE"), but leaves
    # the Analysis, its marker, and its other entry (if any) untouched --
    # whole-analysis deletion lives solely on the marker's delete button
    # (api/images.py's delete_marker).
    project_db.delete(entry)
    project_db.commit()


@router.put("/analyses/{analysis_id}/gap", response_model=AnalysisEntryOut)
def update_gap_entry(
    project_id: int,
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    return _update_entry(project_id, analysis_id, EntryType.GAP, body, db, project_db, current_user)


@router.put("/analyses/{analysis_id}/flush", response_model=AnalysisEntryOut)
def update_flush_entry(
    project_id: int,
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    return _update_entry(project_id, analysis_id, EntryType.FLUSH, body, db, project_db, current_user)


@router.put("/entries/{entry_id}/angled-settings", response_model=AnalysisEntryOut)
def update_angled_settings(
    project_id: int,
    entry_id: int,
    body: AngledSettingsUpdate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    # Deliberately its own narrow endpoint rather than folded into
    # AnalysisEntryCreate/_update_entry -- that schema is a full-replace
    # body built independently by two callers (AnalysisDetailPage.jsx and
    # AnalysisListPage.jsx), and AnalysisListPage's already omits `notes`
    # from its PUT body, silently resetting it on every save. Adding more
    # defaulted fields there would let the same trap reset the angle too.
    require_project_editor(db, current_user, project_id)
    entry = _get_entry_or_404(project_db, project_id, entry_id)

    entry.interface_angle = body.interface_angle
    entry.calculation_method = body.calculation_method
    entry.updated_by_name = f"{current_user.first_name} {current_user.last_name}"
    project_db.commit()
    project_db.refresh(entry)

    analysis = _get_analysis_or_404(project_db, project_id, entry.analysis_id)
    return _entry_out(analysis, entry)
