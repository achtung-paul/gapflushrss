# Builds the .xlsx workbooks for the "export to Excel" feature
# (PROJECT_BRIEF.md step 7: each Gap/Flush analysis, plus a per-Commodity
# summary, exportable to Excel via openpyxl).
#
# Built entirely with openpyxl's own styling API rather than loading a
# stored .xlsx template file: a template would be an opaque binary blob
# in the repo, impossible to review in a diff, whereas every cell here is
# plain, readable Python (same reasoning as core/simulation.py being kept
# as plain functions -- easy to check by hand). See api/exports.py for
# the routes that fetch the data these functions turn into a workbook;
# nothing in this file talks to the database or MinIO directly, so it can
# be tested by just building a workbook from made-up values.

import math
import re
from datetime import datetime, timezone
from io import BytesIO

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

CONTRIBUTOR_TYPE_LABELS = {
    "COMPONENT": "Component tolerance",
    "PROCESS": "Assembly process variation",
}
RAG_LABELS = {
    "green": "Pass",
    "amber": "Caution",
    "red": "Fail",
    "not_evaluated": "Not evaluated",
}
# Same soft-tint colours as index.css's .rag-* classes, so a printed
# sheet reads the same way as the on-screen app.
RAG_FILLS = {
    "green": PatternFill("solid", fgColor="CDECD8"),
    "amber": PatternFill("solid", fgColor="F4D9A0"),
    "red": PatternFill("solid", fgColor="F3C9C9"),
    "not_evaluated": PatternFill("solid", fgColor="E0E0E0"),
}
METHOD_LABELS = {"WORST_CASE": "Worst case", "RSS": "Statistical (RSS)"}
# Confidence a given sigma level represents, carried over from the
# legacy reference report this format is inspired by -- worth keeping as
# it's the kind of thing an engineer reading the report wants next to the
# number, not something this app calculates itself.
SIGMA_CONFIDENCE = {3: "99.73% (Gap plan)", 4: "99.994% (Clearance)", 5: "99.99994% (Functional)"}

HEADING_FONT = Font(bold=True, size=14, color="2E5339")
LABEL_FONT = Font(bold=True, size=10)
SECTION_FONT = Font(bold=True, size=11, color="2E5339")
TABLE_HEADER_FILL = PatternFill("solid", fgColor="2E5339")
TABLE_HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
_THIN_SIDE = Side(style="thin", color="CCCCCC")
THIN_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)

# A4 portrait's full page width at 96 DPI (Excel/openpyxl's assumed
# reference resolution for pixel-sized images) -- the fixed measurement
# "1/3 of an A4 page" / "1/2 of an A4 page" the assembly images below
# are sized against, confirmed with the user to be an absolute size
# rather than relative to whichever sheet/orientation the image actually
# ends up on (the commodity summary sheet is landscape, but its assembly
# images are still sized off this portrait figure).
A4_PORTRAIT_WIDTH_PX = 794
# Excel's default row height (~15pt) in pixels -- used to convert an
# embedded image's pixel height into a number of rows to advance past,
# so the next section doesn't overlap it.
ROW_HEIGHT_PX = 20
# Same green as --color-heading in index.css -- the on-screen balloon
# marker's fill colour, reused here so a marker drawn onto an exported
# photo looks like the same marker shown in the app.
BALLOON_FILL = (0x3F, 0x82, 0x59)


def _setup_a4(ws: Worksheet, orientation: str = "portrait") -> None:
    """Configure a worksheet to print cleanly on A4.

    fitToWidth=1 / fitToHeight=0 scales the whole sheet down to exactly
    one page wide (as many pages tall as needed) regardless of how many
    columns a table ends up needing -- more robust than hand-tuning
    column widths, which would break the moment a description or note is
    a little longer than expected.
    """
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = orientation
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = 0.4
    ws.page_margins.right = 0.4
    ws.page_margins.top = 0.5
    ws.page_margins.bottom = 0.5
    ws.page_margins.header = 0.2
    ws.page_margins.footer = 0.2
    ws.print_options.horizontalCentered = True


# The notes editor (RichTextEditor.jsx) can only ever emit tags from
# core/html_sanitize.py's ALLOWED_TAGS, and sanitize_notes() has already
# run on this value before it was stored -- so a plain regex strip is
# safe here even though it would not be safe against arbitrary HTML.
_BLOCK_TAG_RE = re.compile(r"</(p|li|h[1-6]|blockquote|pre)>|<br\s*/?>|<hr\s*/?>", re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def notes_html_to_text(notes_html: str) -> str:
    """Turn sanitised rich-text notes into plain text for a cell -- a
    cell can't render markup, so block-level tags become newlines and
    everything else is stripped."""
    text = _BLOCK_TAG_RE.sub("\n", notes_html)
    text = _ANY_TAG_RE.sub("", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text.strip()


def _draw_markers(image_bytes: bytes, markers: list[dict]) -> bytes:
    """Draw each marker's leader-line polyline and numbered balloon onto
    a copy of the assembly image.

    markers: [{"x": float 0-1, "y": float 0-1, "sequence_number": int,
    "points": list[[float, float]]}]. x/y and points are fractions of
    the image's own natural size (same convention as models/marker.py),
    so they map straight onto pixel coordinates once the image is
    opened -- no display-size transform needed. Returns new PNG bytes;
    the original bytes are left untouched.
    """
    image = PILImage.open(BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    # Scaled to the photo's own resolution, not a fixed pixel size --
    # index.css's 24px .balloon-marker assumes a screen-sized display
    # image; a full-resolution photo needs a proportionally bigger
    # circle to stay legible.
    radius = max(width, height) * 0.018
    line_width = max(2, int(radius * 0.25))
    font = ImageFont.load_default(size=max(8, int(radius * 1.1)))

    # Leader lines first, so every balloon is drawn on top of them --
    # matches the on-screen stacking order (.marker-wrap sits above
    # .marker-polylines in index.css). Same red as .marker-polylines
    # polyline's stroke there (#d32f2f).
    for marker in markers:
        points_px = [(px * width, py * height) for px, py in marker["points"]]
        if len(points_px) >= 2:
            draw.line(points_px, fill=(0xD3, 0x2F, 0x2F), width=line_width, joint="curve")

    for marker in markers:
        cx = marker["x"] * width
        cy = marker["y"] * height
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=BALLOON_FILL,
            outline=(255, 255, 255),
            width=max(2, int(radius * 0.15)),
        )
        text = str(marker["sequence_number"])
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_width, text_height = right - left, bottom - top
        draw.text(
            (cx - text_width / 2 - left, cy - text_height / 2 - top),
            text,
            fill=(255, 255, 255),
            font=font,
        )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _embed_image(ws: Worksheet, data: bytes, cell: str, target_width: int) -> int:
    """Insert an image anchored at `cell`, scaled to target_width px with
    its aspect ratio preserved. Returns the scaled height in px, so the
    caller can work out how many rows to advance before writing
    anything else into the sheet."""
    xl_image = XLImage(BytesIO(data))
    xl_image.height = int(xl_image.height * (target_width / xl_image.width))
    xl_image.width = target_width
    ws.add_image(xl_image, cell)
    return xl_image.height


def _label_value_row(ws: Worksheet, row: int, label1: str, value1: str, label2: str = "", value2: str = "") -> None:
    ws.cell(row=row, column=1, value=label1).font = LABEL_FONT
    ws.cell(row=row, column=2, value=value1)
    if label2:
        ws.cell(row=row, column=5, value=label2).font = LABEL_FONT
        ws.cell(row=row, column=6, value=value2)


def _section_title(ws: Worksheet, row: int, title: str) -> None:
    ws.cell(row=row, column=1, value=title).font = SECTION_FONT


def _table_header(ws: Worksheet, row: int, headers: list[str]) -> None:
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=text)
        cell.font = TABLE_HEADER_FONT
        cell.fill = TABLE_HEADER_FILL
        cell.border = THIN_BORDER


def _table_row(ws: Worksheet, row: int, values: list, wrap_columns: set[int] | None = None) -> None:
    wrap_columns = wrap_columns or set()
    for col, value in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.border = THIN_BORDER
        if col in wrap_columns:
            cell.alignment = WRAP_TOP


def build_entry_workbook(
    *,
    project_name: str,
    commodity_name: str,
    commodity_code: str,
    project_id: int,
    analysis_id: int,
    display_code: str,
    description: str,
    entry_type: str,
    direction: str | None,
    created_by_name: str,
    updated_by_name: str,
    nominal_value: float,
    upper_limit: float,
    lower_limit: float,
    notes_html: str,
    frontend_origin: str,
    chain_components: list[dict] | None = None,
    simulation: dict | None = None,
    angled_components: list[dict] | None = None,
    angled_simulation: dict | None = None,
    images: list[tuple[str, bytes]] | None = None,
    assembly_image: tuple[str, bytes] | None = None,
) -> bytes:
    """Build one Gap or Flush entry's report as an .xlsx file (bytes).

    Pass chain_components/simulation for a linear entry (direction is
    X/Y/Z/None), or angled_components/angled_simulation for an angled one
    (direction == 'OTHER') -- exactly one pair is expected, matching
    AnalysisReportPage.jsx's own either/or branch.

    assembly_image, if given, is (filename, bytes) for the Commodity's
    assembly photo with only *this* entry's own marker already drawn
    onto it (see api/exports.py -- drawing happens before this function
    is called, since core/excel_export.py has no DB access to look the
    marker up itself).
    """
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Analysis"
    _setup_a4(ws, orientation="portrait")

    ws.column_dimensions["A"].width = 6
    for letter in "BCDEFGH":
        ws.column_dimensions[letter].width = 16
    ws.column_dimensions["C"].width = 26
    ws.column_dimensions["H"].width = 24

    ws.merge_cells("A1:H1")
    ws["A1"] = "GapFit Pro -- Analysis Report"
    ws["A1"].font = HEADING_FONT

    row = 3
    _label_value_row(ws, row, "Project:", project_name, "Commodity:", f"{commodity_name} ({commodity_code})")
    row += 1
    _label_value_row(ws, row, "Analysis:", display_code, "Description:", description or "--")
    row += 1
    _label_value_row(ws, row, "Gap/Flush:", entry_type.title(), "Direction:", direction or "--")
    row += 1
    _label_value_row(ws, row, "Created by:", created_by_name, "Last modified by:", updated_by_name)
    row += 1
    export_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    link_cell_row = row
    _label_value_row(ws, row, "Exported:", export_date)
    link_cell = ws.cell(row=link_cell_row, column=5, value="Open in GapFit Pro")
    link_cell.hyperlink = f"{frontend_origin}/projects/{project_id}/analyses/{analysis_id}"
    link_cell.font = Font(color="1155CC", underline="single")
    row += 2

    if assembly_image:
        _section_title(ws, row, "Location on assembly")
        row += 1
        _, image_data = assembly_image
        height_px = _embed_image(ws, image_data, f"A{row}", A4_PORTRAIT_WIDTH_PX // 3)
        row += math.ceil(height_px / ROW_HEIGHT_PX) + 2

    _section_title(ws, row, "Target band")
    row += 1
    _table_header(ws, row, ["Nominal (mm)", "Upper limit (mm)", "Lower limit (mm)", "Band min (mm)", "Band max (mm)"])
    row += 1
    _table_row(
        ws,
        row,
        [nominal_value, upper_limit, lower_limit, nominal_value - lower_limit, nominal_value + upper_limit],
    )
    row += 2

    is_angled = angled_components is not None
    if is_angled:
        _section_title(ws, row, "Angled interface")
        row += 1
        _label_value_row(
            ws,
            row,
            "Interface angle:",
            f"{angled_simulation['interface_angle']}°",
            "Method:",
            METHOD_LABELS.get(angled_simulation["calculation_method"], angled_simulation["calculation_method"]),
        )
        row += 2

        _table_header(ws, row, ["#", "Component", "X tolerance (± mm)", "Y tolerance (± mm)", "Vx (mm)", "Vy (mm)"])
        row += 1
        if not angled_components:
            ws.cell(row=row, column=1, value="No angled components recorded.")
            row += 1
        else:
            for component in angled_components:
                _table_row(
                    ws,
                    row,
                    [
                        component["sequence_number"],
                        component["component_name"],
                        component["x_tolerance"],
                        component["y_tolerance"],
                        round(component["vx"], 3),
                        round(component["vy"], 3),
                    ],
                    wrap_columns={2},
                )
                row += 1
        row += 1

        _section_title(ws, row, "Results")
        row += 1
        _table_header(ws, row, ["Total variation (± mm)", "Predicted range (mm)", "RAG"])
        row += 1
        rag = angled_simulation["rag"]
        _table_row(
            ws,
            row,
            [
                round(angled_simulation["total_variation"], 3),
                f"{angled_simulation['lower_bound']:.3f} to {angled_simulation['upper_bound']:.3f}",
                RAG_LABELS.get(rag, rag),
            ],
        )
        ws.cell(row=row, column=3).fill = RAG_FILLS.get(rag, RAG_FILLS["not_evaluated"])
        row += 2
    else:
        _section_title(ws, row, "Tolerance chain")
        row += 1
        _table_header(
            ws,
            row,
            ["#", "Type", "Description", "Tolerance (± mm)", "Measured (mm)", "Material", "Tolerance group", "Note"],
        )
        row += 1
        if not chain_components:
            ws.cell(row=row, column=1, value="No chain components recorded.")
            row += 1
        else:
            for component in chain_components:
                _table_row(
                    ws,
                    row,
                    [
                        component["sequence_number"],
                        CONTRIBUTOR_TYPE_LABELS.get(component["contributor_type"], component["contributor_type"]),
                        component["description"],
                        component["tolerance_value"],
                        component["measured_value"] if component["measured_value"] is not None else "--",
                        component["material"] or "--",
                        component["tolerance_group_name"] or "--",
                        component["note"] or "--",
                    ],
                    wrap_columns={3, 8},
                )
                row += 1
        row += 1

        _section_title(ws, row, "Results")
        row += 1
        _table_header(ws, row, ["Sigma level", "Confidence", "Spread (± mm)", "Predicted range (mm)", "RAG"])
        row += 1
        for result in simulation["results"]:
            rag = result["rag"]
            _table_row(
                ws,
                row,
                [
                    f"{result['sigma_level']}σ",
                    SIGMA_CONFIDENCE.get(result["sigma_level"], ""),
                    round(result["spread"], 3),
                    f"{result['lower_bound']:.3f} to {result['upper_bound']:.3f}",
                    RAG_LABELS.get(rag, rag),
                ],
            )
            ws.cell(row=row, column=5).fill = RAG_FILLS.get(rag, RAG_FILLS["not_evaluated"])
            row += 1
        row += 1

    if notes_html:
        _section_title(ws, row, "Notes")
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row + 2, end_column=8)
        notes_cell = ws.cell(row=row, column=1, value=notes_html_to_text(notes_html))
        notes_cell.alignment = WRAP_TOP
        row += 4

    if images:
        _section_title(ws, row, "Images")
        row += 1
        # Two per row, matching AnalysisReportPage.jsx's printed gallery
        # (index.css's .report-gallery-grid) -- same 2-up layout on an A4
        # portrait sheet, just in Excel instead of the browser. Each pair
        # advances by its own tallest image's actual height, not a fixed
        # guess -- a guess too short lets a tall photo overlap the pair
        # below it, and every photo's own aspect ratio is different.
        gallery_col_for_slot = {0: "A", 1: "E"}
        for pair_start in range(0, len(images), 2):
            pair = images[pair_start : pair_start + 2]
            pair_heights = [
                _embed_image(ws, data, f"{gallery_col_for_slot[slot]}{row}", 280)
                for slot, (_, data) in enumerate(pair)
            ]
            row += math.ceil(max(pair_heights) / ROW_HEIGHT_PX) + 2

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_commodity_workbook(
    *,
    project_name: str,
    commodity_name: str,
    commodity_code: str,
    rows: list[dict],
    assembly_images: list[tuple[str, bytes]] | None = None,
) -> bytes:
    """Build a Commodity's summary report as an .xlsx file (bytes).

    `rows` is one dict per (analysis x Gap) / (analysis x Flush) pair,
    matching CommodityReportPage.jsx's flatMap -- rows exist even where
    the entry itself is null, each with keys: analysis_code,
    description, entry_label ('Gap'/'Flush'), direction, nominal_value,
    lower_limit, upper_limit, rag_by_sigma (dict of 3/4/5 -> rag string
    or None), updated_by_name.

    assembly_images, if given, is a list of (filename, bytes) -- every
    image belonging to this Commodity, with *every* marker on it already
    drawn (see api/exports.py, same reasoning as build_entry_workbook's
    assembly_image). Shown above the analysis table, one per row since
    each is sized to half the sheet's width.
    """
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Commodity summary"
    # Landscape, not portrait -- this table has too many columns
    # (11) to stay legible on a portrait page even scaled to fit, unlike
    # the single-entry report above.
    _setup_a4(ws, orientation="landscape")

    widths = [14, 24, 10, 10, 14, 14, 14, 10, 10, 10, 18]
    for letter, width in zip("ABCDEFGHIJK", widths):
        ws.column_dimensions[letter].width = width

    ws.merge_cells("A1:K1")
    ws["A1"] = "GapFit Pro -- Commodity Report"
    ws["A1"].font = HEADING_FONT

    row = 3
    _label_value_row(ws, row, "Project:", project_name, "Commodity:", f"{commodity_name} ({commodity_code})")
    row += 1
    export_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _label_value_row(ws, row, "Exported:", export_date)
    row += 2

    if assembly_images:
        _section_title(ws, row, "Assembly")
        row += 1
        for _, image_data in assembly_images:
            height_px = _embed_image(ws, image_data, f"A{row}", A4_PORTRAIT_WIDTH_PX // 2)
            row += math.ceil(height_px / ROW_HEIGHT_PX) + 1
        row += 1

    headers = [
        "Analysis",
        "Description",
        "Gap/Flush",
        "Direction",
        "Nominal (mm)",
        "Band min (mm)",
        "Band max (mm)",
        "3σ RAG",
        "4σ RAG",
        "5σ RAG",
        "Last modified by",
    ]
    _table_header(ws, row, headers)
    row += 1

    if not rows:
        ws.cell(row=row, column=1, value="No analyses yet.")
        row += 1
    else:
        for entry_row in rows:
            has_entry = entry_row["nominal_value"] is not None
            band_min = entry_row["nominal_value"] - entry_row["lower_limit"] if has_entry else None
            band_max = entry_row["nominal_value"] + entry_row["upper_limit"] if has_entry else None
            values = [
                entry_row["analysis_code"],
                entry_row["description"] or "--",
                entry_row["entry_label"],
                entry_row["direction"] or "--",
                entry_row["nominal_value"] if has_entry else "--",
                band_min if band_min is not None else "--",
                band_max if band_max is not None else "--",
            ]
            for sigma in (3, 4, 5):
                rag = entry_row["rag_by_sigma"].get(sigma)
                values.append(RAG_LABELS.get(rag, "--") if rag else "--")
            values.append(entry_row["updated_by_name"] or "--")

            _table_row(ws, row, values, wrap_columns={2})
            for sigma_index, sigma in enumerate((3, 4, 5)):
                rag = entry_row["rag_by_sigma"].get(sigma)
                if rag:
                    ws.cell(row=row, column=8 + sigma_index).fill = RAG_FILLS.get(rag, RAG_FILLS["not_evaluated"])
            row += 1

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
