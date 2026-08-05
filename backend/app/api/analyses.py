# Analyses live under a Commodity, and each gets an auto-generated unique
# ID (commodity code + zero-padded sequence number, e.g. "DR-001"). A Gap
# and/or Flush entry can then be attached to an Analysis -- at least one
# is expected eventually, but the brief explicitly allows an Analysis to
# exist as a placeholder with neither yet, so creating one doesn't require
# a Gap or Flush up front.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_manager
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.analysis_entry import AnalysisEntry, EntryType
from app.models.commodity import Commodity
from app.models.user import User
from app.schemas.analysis import AnalysisDetailOut, AnalysisOut
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


def _entry_out(analysis: Analysis, entry: AnalysisEntry) -> AnalysisEntryOut:
    return AnalysisEntryOut(
        entry_id=entry.entry_id,
        analysis_id=entry.analysis_id,
        entry_type=entry.entry_type,
        entry_code=f"{analysis.analysis_code}-{entry.entry_type.value}",
        nominal_value=entry.nominal_value,
        upper_limit=entry.upper_limit,
        lower_limit=entry.lower_limit,
    )


@router.get("/commodities/{commodity_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(
    commodity_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return (
        db.query(Analysis)
        .filter(Analysis.commodity_id == commodity_id)
        .order_by(Analysis.sequence_number)
        .all()
    )


@router.post(
    "/commodities/{commodity_id}/analyses",
    response_model=AnalysisOut,
    status_code=status.HTTP_201_CREATED,
)
def create_analysis(
    commodity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    commodity = _get_commodity_or_404(db, commodity_id)
    require_project_manager(db, current_user, commodity.project_id)

    highest_sequence = (
        db.query(func.max(Analysis.sequence_number))
        .filter(Analysis.commodity_id == commodity_id)
        .scalar()
    )
    next_sequence = (highest_sequence or 0) + 1

    analysis = Analysis(
        commodity_id=commodity_id,
        sequence_number=next_sequence,
        analysis_code=f"{commodity.code}-{next_sequence:03d}",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@router.get("/analyses/{analysis_id}", response_model=AnalysisDetailOut)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    analysis = _get_analysis_or_404(db, analysis_id)
    entries = db.query(AnalysisEntry).filter(AnalysisEntry.analysis_id == analysis_id).all()
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
