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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_manager
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.analysis_entry import AnalysisEntry, EntryType
from app.models.commodity import Commodity
from app.models.user import User
from app.schemas.analysis import AnalysisDetailOut
from app.schemas.analysis_entry import AnalysisEntryCreate, AnalysisEntryOut

router = APIRouter(tags=["analyses"])


def _get_commodity_or_404(db: Session, commodity_id: int) -> Commodity:
    commodity = db.get(Commodity, commodity_id)
    if commodity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commodity not found")
    return commodity


def _get_analysis_or_404(db: Session, analysis_id: int) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return analysis


def _get_entry_or_404(db: Session, entry_id: int) -> AnalysisEntry:
    entry = db.get(AnalysisEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
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
    )


def next_analysis_sequence_number(db: Session, commodity_id: int) -> int:
    highest_sequence = (
        db.query(func.max(Analysis.sequence_number))
        .filter(Analysis.commodity_id == commodity_id)
        .scalar()
    )
    return (highest_sequence or 0) + 1


def _analysis_detail_out(db: Session, analysis: Analysis) -> AnalysisDetailOut:
    entries = db.query(AnalysisEntry).filter(AnalysisEntry.analysis_id == analysis.analysis_id).all()
    gap = next((e for e in entries if e.entry_type == EntryType.GAP), None)
    flush = next((e for e in entries if e.entry_type == EntryType.FLUSH), None)

    return AnalysisDetailOut(
        analysis_id=analysis.analysis_id,
        commodity_id=analysis.commodity_id,
        analysis_code=analysis.analysis_code,
        sequence_number=analysis.sequence_number,
        gap=_entry_out(analysis, gap) if gap else None,
        flush=_entry_out(analysis, flush) if flush else None,
    )


@router.get("/commodities/{commodity_id}/analyses", response_model=list[AnalysisDetailOut])
def list_analyses(
    commodity_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    analyses = (
        db.query(Analysis)
        .filter(Analysis.commodity_id == commodity_id)
        .order_by(Analysis.sequence_number)
        .all()
    )
    return [_analysis_detail_out(db, analysis) for analysis in analyses]


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetailOut)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    analysis = _get_analysis_or_404(db, analysis_id)
    return _analysis_detail_out(db, analysis)


def _create_entry(
    analysis_id: int,
    entry_type: EntryType,
    body: AnalysisEntryCreate,
    db: Session,
    current_user: User,
) -> AnalysisEntryOut:
    analysis = _get_analysis_or_404(db, analysis_id)
    commodity = _get_commodity_or_404(db, analysis.commodity_id)
    require_project_manager(db, current_user, commodity.project_id)

    already_exists = (
        db.query(AnalysisEntry)
        .filter_by(analysis_id=analysis_id, entry_type=entry_type)
        .first()
    )
    if already_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{entry_type.value} already attached to this analysis",
        )

    entry = AnalysisEntry(
        analysis_id=analysis_id,
        entry_type=entry_type,
        nominal_value=body.nominal_value,
        upper_limit=body.upper_limit,
        lower_limit=body.lower_limit,
        direction=body.direction,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _entry_out(analysis, entry)


@router.post(
    "/analyses/{analysis_id}/gap",
    response_model=AnalysisEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_gap_entry(
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _create_entry(analysis_id, EntryType.GAP, body, db, current_user)


@router.post(
    "/analyses/{analysis_id}/flush",
    response_model=AnalysisEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_flush_entry(
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _create_entry(analysis_id, EntryType.FLUSH, body, db, current_user)


def _update_entry(
    analysis_id: int,
    entry_type: EntryType,
    body: AnalysisEntryCreate,
    db: Session,
    current_user: User,
) -> AnalysisEntryOut:
    analysis = _get_analysis_or_404(db, analysis_id)
    commodity = _get_commodity_or_404(db, analysis.commodity_id)
    require_project_manager(db, current_user, commodity.project_id)

    entry = db.query(AnalysisEntry).filter_by(analysis_id=analysis_id, entry_type=entry_type).first()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entry_type.value} not attached to this analysis yet",
        )

    entry.nominal_value = body.nominal_value
    entry.upper_limit = body.upper_limit
    entry.lower_limit = body.lower_limit
    entry.direction = body.direction
    db.commit()
    db.refresh(entry)
    return _entry_out(analysis, entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = _get_entry_or_404(db, entry_id)
    analysis = _get_analysis_or_404(db, entry.analysis_id)
    commodity = _get_commodity_or_404(db, analysis.commodity_id)
    require_project_manager(db, current_user, commodity.project_id)

    # Cascades to its chain components (ondelete="CASCADE"), but leaves
    # the Analysis, its marker, and its other entry (if any) untouched --
    # whole-analysis deletion lives solely on the marker's delete button
    # (api/images.py's delete_marker).
    db.delete(entry)
    db.commit()


@router.put("/analyses/{analysis_id}/gap", response_model=AnalysisEntryOut)
def update_gap_entry(
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _update_entry(analysis_id, EntryType.GAP, body, db, current_user)


@router.put("/analyses/{analysis_id}/flush", response_model=AnalysisEntryOut)
def update_flush_entry(
    analysis_id: int,
    body: AnalysisEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _update_entry(analysis_id, EntryType.FLUSH, body, db, current_user)
