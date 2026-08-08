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
from app.models.tolerance_group import ToleranceGroup
from app.models.tolerance_value import ToleranceValue
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


def _resolve_tolerance_group_name(db: Session, tolerance_value_id: int | None) -> str | None:
    """The Tol matrix group name a saved value came from, for display.

    Resolved server-side from tolerance_value_id (a two-hop lookup
    through the central database's ToleranceValue -> ToleranceGroup)
    rather than trusting a client-supplied name -- ToleranceGroup is
    central reference data, chain_components is project-scoped, so this
    can't be a real join; snapshotting the true recorded name here (not
    whatever text a client happened to send) keeps that snapshot honest.
    """
    if tolerance_value_id is None:
        return None
    tolerance_value = db.get(ToleranceValue, tolerance_value_id)
    if tolerance_value is None:
        return None
    group = db.get(ToleranceGroup, tolerance_value.tolerance_group_id)
    return group.name if group else None


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
        note=body.note,
        measured_value=body.measured_value,
        material=body.material,
        tolerance_group_name=_resolve_tolerance_group_name(db, body.tolerance_value_id),
    )
    project_db.add(component)
    project_db.commit()
    project_db.refresh(component)
    return component


@router.put("/chain-components/{chain_component_id}", response_model=ChainComponentOut)
def update_chain_component(
    project_id: int,
    chain_component_id: int,
    body: ChainComponentCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    component = project_db.get(ChainComponent, chain_component_id)
    if component is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain component not found")

    # Editor-level, same as create -- this changes an existing
    # contributor's values, it doesn't remove one, so it's not held to
    # the Manager-only bar delete_chain_component below uses.
    _require_editor_for_entry(db, project_db, current_user, project_id, component.entry_id)

    component.contributor_type = body.contributor_type
    component.description = body.description
    component.tolerance_value = body.tolerance_value
    component.tolerance_value_id = body.tolerance_value_id
    component.note = body.note
    component.measured_value = body.measured_value
    component.material = body.material
    # Re-resolved rather than left as-is: tolerance_value_id itself is
    # sent back unchanged by the edit form (see the class comment on
    # ChainComponentCreate's tolerance_value_id), so in practice this
    # just re-derives the same id's current name -- which also means an
    # admin renaming a Tol matrix group is reflected here on next save,
    # since this is a display label, not a calculation input like
    # tolerance_value itself.
    component.tolerance_group_name = _resolve_tolerance_group_name(db, body.tolerance_value_id)
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
