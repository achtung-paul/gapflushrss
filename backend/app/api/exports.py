# Excel exports of the same two reports AnalysisReportPage.jsx and
# CommodityReportPage.jsx render for printing (PROJECT_BRIEF.md step 7:
# "exportable to Excel via openpyxl"). Deliberately re-derives everything
# from the ORM rather than calling get_simulation/get_analysis over HTTP
# -- both are plain functions this module can call directly, so there's
# no reason to pay for a second request just to get the same numbers.

import re
from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.analyses import _get_analysis_or_404, _get_commodity_or_404, _get_entry_or_404
from app.api.deps import get_current_user, get_project, get_project_db, get_project_minio_service
from app.api.reference_data import get_visible_sigma_levels
from app.core import service_storage
from app.core.angled_simulation import run_angled_simulation
from app.core.config import settings
from app.core.excel_export import _draw_markers, build_commodity_workbook, build_entry_workbook
from app.core.simulation import run_simulation
from app.db.session import get_db
from app.models.analysis import Analysis
from app.models.analysis_entry import AnalysisEntry, Direction, EntryType
from app.models.analysis_image import AnalysisImage
from app.models.angled_component import AngledComponent
from app.models.chain_component import ChainComponent
from app.models.image import Image
from app.models.marker import Marker
from app.models.minio_service import MinioService
from app.models.project import Project
from app.models.user import User

router = APIRouter(prefix="/projects/{project_id}", tags=["exports"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_filename_part(text: str) -> str:
    """Turn a user-entered name (Project/Commodity, free text with no
    format rules) into a filename-safe fragment -- strips anything that
    isn't a letter, digit, space, or hyphen, then collapses whitespace,
    so a stray slash or colon in a name can't break the
    Content-Disposition header or produce a bad filename on any OS.
    """
    cleaned = re.sub(r"[^A-Za-z0-9 \-]", "", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _read_image_bytes(minio_service: MinioService, object_key: str) -> bytes:
    response = service_storage.get_image_stream(minio_service, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


@router.get("/entries/{entry_id}/export")
def export_entry(
    project_id: int,
    entry_id: int,
    project: Project = Depends(get_project),
    project_db: Session = Depends(get_project_db),
    db: Session = Depends(get_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
):
    """Download one Gap or Flush entry's report as .xlsx."""
    entry = _get_entry_or_404(project_db, project_id, entry_id)
    analysis = _get_analysis_or_404(project_db, project_id, entry.analysis_id)
    commodity = _get_commodity_or_404(project_db, project_id, analysis.commodity_id)

    display_code = analysis.analysis_code + "-" + entry.entry_type.value
    if entry.direction:
        display_code += "-" + entry.direction.value

    images = (
        project_db.query(AnalysisImage)
        .filter(AnalysisImage.entry_id == entry_id)
        .order_by(AnalysisImage.uploaded_at)
        .all()
    )
    image_data = [
        (image.original_filename, _read_image_bytes(minio_service, image.object_key)) for image in images
    ]

    # Marker.analysis_id is unique (models/marker.py) -- an Analysis only
    # ever comes into being as the side effect of dropping a marker (see
    # api/images.py's create_marker), so there's exactly one row here,
    # not a list to filter down.
    assembly_image = None
    marker = project_db.query(Marker).filter(Marker.analysis_id == analysis.analysis_id).first()
    if marker is not None:
        assembly = project_db.get(Image, marker.image_id)
        raw_bytes = _read_image_bytes(minio_service, assembly.object_key)
        this_marker = [
            {"x": marker.x, "y": marker.y, "sequence_number": analysis.sequence_number, "points": marker.points}
        ]
        assembly_image = (assembly.original_filename, _draw_markers(raw_bytes, this_marker))

    common_kwargs = dict(
        project_name=project.project_name,
        commodity_name=commodity.name,
        commodity_code=commodity.code,
        project_id=project_id,
        analysis_id=analysis.analysis_id,
        display_code=display_code,
        description=analysis.description,
        entry_type=entry.entry_type.value,
        direction=entry.direction.value if entry.direction else None,
        created_by_name=entry.created_by_name,
        updated_by_name=entry.updated_by_name,
        nominal_value=float(entry.nominal_value),
        upper_limit=float(entry.upper_limit),
        lower_limit=float(entry.lower_limit),
        notes_html=entry.notes,
        frontend_origin=settings.frontend_origin,
        images=image_data,
        assembly_image=assembly_image,
    )

    if entry.direction == Direction.OTHER:
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
        # Zip resolved vx/vy back onto each component -- same as
        # api/angled_components.py's get_angled_simulation, both derive
        # from the same sequence_number-ordered query.
        angled_components = [
            {
                "sequence_number": component.sequence_number,
                "component_name": component.component_name,
                "x_tolerance": float(component.x_tolerance),
                "y_tolerance": float(component.y_tolerance),
                "vx": vx,
                "vy": vy,
            }
            for component, (vx, vy) in zip(components, simulation["rows"])
        ]
        workbook_bytes = build_entry_workbook(
            **common_kwargs,
            angled_components=angled_components,
            angled_simulation={
                "interface_angle": float(entry.interface_angle),
                "calculation_method": entry.calculation_method.value,
                "total_variation": simulation["total_variation"],
                "lower_bound": simulation["lower_bound"],
                "upper_bound": simulation["upper_bound"],
                "rag": simulation["rag"],
            },
        )
    else:
        components = (
            project_db.query(ChainComponent)
            .filter(ChainComponent.entry_id == entry_id)
            .order_by(ChainComponent.sequence_number)
            .all()
        )
        info_only_by_level = get_visible_sigma_levels(db, current_user.client_id)
        simulation = run_simulation(
            [float(component.tolerance_value) for component in components],
            nominal=float(entry.nominal_value),
            upper_limit=float(entry.upper_limit),
            lower_limit=float(entry.lower_limit),
            sigma_levels=list(info_only_by_level.keys()),
        )
        simulation["results"] = [
            {**row, "info_only": info_only_by_level[row["sigma_level"]]} for row in simulation["results"]
        ]
        chain_components = [
            {
                "sequence_number": component.sequence_number,
                "contributor_type": component.contributor_type.value,
                "description": component.description,
                "tolerance_value": float(component.tolerance_value),
                "measured_value": (
                    float(component.measured_value) if component.measured_value is not None else None
                ),
                "material": component.material,
                "tolerance_group_name": component.tolerance_group_name,
                "note": component.note,
            }
            for component in components
        ]
        workbook_bytes = build_entry_workbook(
            **common_kwargs,
            chain_components=chain_components,
            simulation=simulation,
        )

    filename_parts = [_safe_filename_part(project.project_name), _safe_filename_part(commodity.name), display_code]
    filename = " - ".join(part for part in filename_parts if part) + ".xlsx"

    return StreamingResponse(
        BytesIO(workbook_bytes),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/commodities/{commodity_id}/export")
def export_commodity(
    project_id: int,
    commodity_id: int,
    project: Project = Depends(get_project),
    project_db: Session = Depends(get_project_db),
    db: Session = Depends(get_db),
    minio_service: MinioService = Depends(get_project_minio_service),
    current_user: User = Depends(get_current_user),
):
    """Download a Commodity's summary report as .xlsx."""
    commodity = _get_commodity_or_404(project_db, project_id, commodity_id)
    info_only_by_level = get_visible_sigma_levels(db, current_user.client_id)
    sigma_levels = list(info_only_by_level.keys())

    # Every image belonging to this commodity, each with *every* marker
    # on it drawn -- unlike export_entry above, which only draws the one
    # marker for that entry's own analysis.
    assembly_images = []
    commodity_images = (
        project_db.query(Image).filter(Image.commodity_id == commodity_id).order_by(Image.uploaded_at).all()
    )
    for image in commodity_images:
        marker_rows = (
            project_db.query(Marker, Analysis)
            .join(Analysis, Marker.analysis_id == Analysis.analysis_id)
            .filter(Marker.image_id == image.image_id)
            .order_by(Analysis.sequence_number)
            .all()
        )
        markers = [
            {"x": marker.x, "y": marker.y, "sequence_number": analysis.sequence_number, "points": marker.points}
            for marker, analysis in marker_rows
        ]
        raw_bytes = _read_image_bytes(minio_service, image.object_key)
        marked_bytes = _draw_markers(raw_bytes, markers) if markers else raw_bytes
        assembly_images.append((image.original_filename, marked_bytes))

    analyses = (
        project_db.query(Analysis)
        .filter(Analysis.commodity_id == commodity_id)
        .order_by(Analysis.sequence_number)
        .all()
    )

    rows = []
    for analysis in analyses:
        entries = (
            project_db.query(AnalysisEntry).filter(AnalysisEntry.analysis_id == analysis.analysis_id).all()
        )
        gap = next((e for e in entries if e.entry_type == EntryType.GAP), None)
        flush = next((e for e in entries if e.entry_type == EntryType.FLUSH), None)

        for entry_label, entry in (("Gap", gap), ("Flush", flush)):
            if entry is None:
                rows.append(
                    {
                        "analysis_code": analysis.analysis_code,
                        "description": analysis.description,
                        "entry_label": entry_label,
                        "direction": None,
                        "nominal_value": None,
                        "lower_limit": None,
                        "upper_limit": None,
                        "rag_by_sigma": {},
                        "updated_by_name": None,
                    }
                )
                continue

            # Always the linear simulation, even for an angled (direction
            # == OTHER) entry -- matches CommodityReportPage.jsx's own
            # summary table, which does the same, so this export and the
            # printed report never disagree with each other.
            components = (
                project_db.query(ChainComponent)
                .filter(ChainComponent.entry_id == entry.entry_id)
                .order_by(ChainComponent.sequence_number)
                .all()
            )
            simulation = run_simulation(
                [float(c.tolerance_value) for c in components],
                nominal=float(entry.nominal_value),
                upper_limit=float(entry.upper_limit),
                lower_limit=float(entry.lower_limit),
                sigma_levels=sigma_levels,
            )
            rag_by_sigma = {result["sigma_level"]: result["rag"] for result in simulation["results"]}

            rows.append(
                {
                    "analysis_code": analysis.analysis_code,
                    "description": analysis.description,
                    "entry_label": entry_label,
                    "direction": entry.direction.value if entry.direction else None,
                    "nominal_value": float(entry.nominal_value),
                    "lower_limit": float(entry.lower_limit),
                    "upper_limit": float(entry.upper_limit),
                    "rag_by_sigma": rag_by_sigma,
                    "updated_by_name": entry.updated_by_name,
                }
            )

    workbook_bytes = build_commodity_workbook(
        project_name=project.project_name,
        commodity_name=commodity.name,
        commodity_code=commodity.code,
        rows=rows,
        sigma_levels=sigma_levels,
        info_only_by_level=info_only_by_level,
        assembly_images=assembly_images,
    )

    filename_parts = [
        _safe_filename_part(project.project_name),
        _safe_filename_part(commodity.name),
        commodity.code,
        "Summary",
    ]
    filename = " - ".join(part for part in filename_parts if part) + ".xlsx"

    return StreamingResponse(
        BytesIO(workbook_bytes),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
