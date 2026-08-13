# Angled-interface tolerance table + simulation for a Gap/Flush entry
# whose direction is OTHER (see models/analysis_entry.py). Deliberately a
# separate file/router/table from chain_components.py -- see
# models/angled_component.py's header for why the two aren't merged.

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.analyses import _get_entry_or_404
from app.api.deps import get_current_user, get_project_db, require_project_editor, require_project_manager
from app.core.angled_simulation import run_angled_simulation
from app.core.security_events import EVENT_DATA_DELETED, record_event
from app.db.session import get_db
from app.models.analysis_entry import AnalysisEntry
from app.models.angled_component import AngledComponent
from app.models.user import User
from app.schemas.angled_component import (
    AngledComponentCreate,
    AngledComponentOut,
    AngledSimulationOut,
    AngledSimulationRow,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["angled-components"])


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


@router.get("/entries/{entry_id}/angled-components", response_model=list[AngledComponentOut])
def list_angled_components(
    project_id: int,
    entry_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    _get_entry_or_404(project_db, project_id, entry_id)
    return (
        project_db.query(AngledComponent)
        .filter(AngledComponent.entry_id == entry_id)
        .order_by(AngledComponent.sequence_number)
        .all()
    )


@router.post(
    "/entries/{entry_id}/angled-components",
    response_model=AngledComponentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_angled_component(
    project_id: int,
    entry_id: int,
    body: AngledComponentCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    _require_editor_for_entry(db, project_db, current_user, project_id, entry_id)

    highest_sequence = (
        project_db.query(func.max(AngledComponent.sequence_number))
        .filter(AngledComponent.entry_id == entry_id)
        .scalar()
    )
    next_sequence = (highest_sequence or 0) + 1

    component = AngledComponent(
        entry_id=entry_id,
        sequence_number=next_sequence,
        component_name=body.component_name,
        x_tolerance=body.x_tolerance,
        y_tolerance=body.y_tolerance,
        note=body.note,
    )
    project_db.add(component)
    project_db.commit()
    project_db.refresh(component)
    return component


@router.put("/angled-components/{angled_component_id}", response_model=AngledComponentOut)
def update_angled_component(
    project_id: int,
    angled_component_id: int,
    body: AngledComponentCreate,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    component = project_db.get(AngledComponent, angled_component_id)
    if component is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angled component not found")

    # Editor-level, same as create -- this changes an existing row's
    # values, it doesn't remove one, so it's not held to the Manager-only
    # bar delete_angled_component below uses.
    _require_editor_for_entry(db, project_db, current_user, project_id, component.entry_id)

    component.component_name = body.component_name
    component.x_tolerance = body.x_tolerance
    component.y_tolerance = body.y_tolerance
    component.note = body.note
    project_db.commit()
    project_db.refresh(component)
    return component


@router.delete("/angled-components/{angled_component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_angled_component(
    request: Request,
    project_id: int,
    angled_component_id: int,
    db: Session = Depends(get_db),
    project_db: Session = Depends(get_project_db),
    current_user: User = Depends(get_current_user),
):
    component = project_db.get(AngledComponent, angled_component_id)
    if component is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Angled component not found")

    # Ownership check happens inside here (via _get_entry_or_404's chain
    # up to Commodity.project_id) -- a colocated project on the same
    # Postgres service could otherwise have a matching angled_component_id.
    _require_manager_for_entry(db, project_db, current_user, project_id, component.entry_id)
    component_name = component.component_name

    project_db.delete(component)
    project_db.commit()

    # See api/chain_components.py's delete_chain_component for why this
    # is a separate commit on the central `db`.
    record_event(
        db,
        event_type=EVENT_DATA_DELETED,
        actor=current_user,
        request=request,
        client_id=current_user.client_id,
        target_type="angled_component",
        target_id=angled_component_id,
        target_name=component_name,
    )
    db.commit()


@router.get("/entries/{entry_id}/angled-simulation", response_model=AngledSimulationOut)
def get_angled_simulation(
    project_id: int,
    entry_id: int,
    project_db: Session = Depends(get_project_db),
    _: User = Depends(get_current_user),
):
    entry = _get_entry_or_404(project_db, project_id, entry_id)
    components = (
        project_db.query(AngledComponent)
        .filter(AngledComponent.entry_id == entry_id)
        .order_by(AngledComponent.sequence_number)
        .all()
    )
    simulation = run_angled_simulation(
        [(float(c.x_tolerance), float(c.y_tolerance)) for c in components],
        angle_degrees=float(entry.interface_angle),
        method=entry.calculation_method.value,
        nominal=float(entry.nominal_value),
        upper_limit=float(entry.upper_limit),
        lower_limit=float(entry.lower_limit),
    )
    # simulation["rows"] is in the same order as `components` (both derive
    # from the same sequence_number-ordered query) -- zip rather than
    # re-query, so this stays one source of truth for the resolution maths.
    rows = [
        AngledSimulationRow(
            angled_component_id=component.angled_component_id,
            component_name=component.component_name,
            x_tolerance=float(component.x_tolerance),
            y_tolerance=float(component.y_tolerance),
            vx=row["vx"],
            vy=row["vy"],
        )
        for component, row in zip(components, simulation["rows"])
    ]
    return AngledSimulationOut(
        interface_angle=float(entry.interface_angle),
        calculation_method=entry.calculation_method,
        total_variation=simulation["total_variation"],
        lower_bound=simulation["lower_bound"],
        upper_bound=simulation["upper_bound"],
        rag=simulation["rag"],
        rows=rows,
    )
