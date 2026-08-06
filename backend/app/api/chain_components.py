# Tolerance chain builder + RSS simulation for a Gap/Flush entry (brief
# steps 4-6): the component tolerances and assembly-process variations
# that feed into the RSS stack-up, and the computed 3/4/5 sigma results
# evaluated against the entry's own nominal/tolerance band.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.analyses import _get_commodity_or_404
from app.api.deps import get_current_user, require_project_manager
from app.core.simulation import run_simulation
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.analysis_entry import AnalysisEntry
from app.models.chain_component import ChainComponent
from app.models.user import User
from app.schemas.chain_component import ChainComponentCreate, ChainComponentOut, SimulationResultOut

router = APIRouter(tags=["chain-components"])


def _get_entry_or_404(db: Session, entry_id: int) -> AnalysisEntry:
    entry = db.get(AnalysisEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry


def _require_manager_for_entry(db: Session, user: User, entry_id: int) -> AnalysisEntry:
    entry = _get_entry_or_404(db, entry_id)
    analysis = db.get(Analysis, entry.analysis_id)
    commodity = _get_commodity_or_404(db, analysis.commodity_id)
    require_project_manager(db, user, commodity.project_id)
    return entry


@router.get("/entries/{entry_id}/chain-components", response_model=list[ChainComponentOut])
def list_chain_components(
    entry_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_entry_or_404(db, entry_id)
    return (
        db.query(ChainComponent)
        .filter(ChainComponent.entry_id == entry_id)
        .order_by(ChainComponent.sequence_number)
        .all()
    )


@router.post(
    "/entries/{entry_id}/chain-components",
    response_model=ChainComponentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_chain_component(
    entry_id: int,
    body: ChainComponentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manager_for_entry(db, current_user, entry_id)

    highest_sequence = (
        db.query(func.max(ChainComponent.sequence_number))
        .filter(ChainComponent.entry_id == entry_id)
        .scalar()
    )
    next_sequence = (highest_sequence or 0) + 1

    component = ChainComponent(
        entry_id=entry_id,
        sequence_number=next_sequence,
        contributor_type=body.contributor_type,
        description=body.description,
        tolerance_value=body.tolerance_value,
        tolerance_value_id=body.tolerance_value_id,
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


@router.delete("/chain-components/{chain_component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chain_component(
    chain_component_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    component = db.get(ChainComponent, chain_component_id)
    if component is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain component not found")

    _require_manager_for_entry(db, current_user, component.entry_id)

    db.delete(component)
    db.commit()


@router.get("/entries/{entry_id}/simulation", response_model=SimulationResultOut)
def get_simulation(
    entry_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    entry = _get_entry_or_404(db, entry_id)
    components = (
        db.query(ChainComponent)
        .filter(ChainComponent.entry_id == entry_id)
        .order_by(ChainComponent.sequence_number)
        .all()
    )
    tolerance_values = [float(component.tolerance_value) for component in components]
    simulation = run_simulation(
        tolerance_values,
        nominal=float(entry.nominal_value),
        upper_limit=float(entry.upper_limit),
        lower_limit=float(entry.lower_limit),
    )
    return SimulationResultOut(**simulation)
