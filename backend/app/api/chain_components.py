# Tolerance chain builder + RSS simulation for a Gap/Flush entry (brief
# steps 4-6): the component tolerances and assembly-process variations
# that feed into the RSS stack-up, and the computed 3/4/5 sigma results
# evaluated against the entry's own nominal/tolerance band.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.analyses import _get_entry_or_404
from app.api.deps import get_current_user, get_project_db, require_project_editor, require_project_manager
from app.core.simulation import run_simulation
from app.db.session import get_db
from app.models.analysis_entry import AnalysisEntry
from app.models.chain_component import ChainComponent
from app.models.user import User
from app.schemas.chain_component import ChainComponentCreate, ChainComponentOut, SimulationResultOut

router = APIRouter(prefix="/projects/{project_id}", tags=["chain-components"])


def _require_editor_for_entry(
    db: Session, project_db: Session, user: User, project_id: int, entry_id: int
) -> AnalysisEntry:
    require_project_editor(db, user, project_id)
    return _get_entry_or_404(project_db, project_id, entry_id)


def _require_manager_for_entry(
    db: Session, project_db: Session, user: User, project_id: int, entry_id: int
) -> AnalysisEntry:
    require_project_manager(db, user, project_id)
    return _get_entry_or_404(project_db, project_id, entry_id)


@router.get("/entries/{entry_id}/chain-components", response_model=list[ChainComponentOut])
def list_chain_components(
    project_id: int,
    entry_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    _get_entry_or_404(project_db, project_id, entry_id)
    return (
        project_db.query(ChainComponent)
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
    project_id: int,
    entry_id: int,
    body: ChainComponentCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    _require_editor_for_entry(db, project_db, current_user, project_id, entry_id)

    highest_sequence = (
        project_db.query(func.max(ChainComponent.sequence_number))
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
    project_db.add(component)
    project_db.commit()
    project_db.refresh(component)
    return component


@router.delete("/chain-components/{chain_component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chain_component(
    project_id: int,
    chain_component_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    component = project_db.get(ChainComponent, chain_component_id)
    if component is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain component not found")

    # Ownership check happens inside here (via _get_entry_or_404's chain
    # up to Commodity.project_id) -- a colocated project on the same
    # Postgres service could otherwise have a matching chain_component_id.
    _require_manager_for_entry(db, project_db, current_user, project_id, component.entry_id)

    project_db.delete(component)
    project_db.commit()


@router.get("/entries/{entry_id}/simulation", response_model=SimulationResultOut)
def get_simulation(
    project_id: int,
    entry_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    entry = _get_entry_or_404(project_db, project_id, entry_id)
    components = (
        project_db.query(ChainComponent)
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
