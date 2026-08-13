# Parses a CSV export of a tolerance table (an industrial tolerance
# standard, or a company's own equivalent) into the shape
# api/reference_data.py needs to create a new ProcessType and its whole
# matrix in one go. Deliberately plain functions with no DB/FastAPI
# imports -- same testable-in-isolation convention as core/simulation.py
# and core/angled_simulation.py.
#
# Two supported file shapes, auto-detected -- see parse_tolerance_csv.
#
# Format 1 (see tolerance_table_EXAMPLE.csv, shared for context only --
# never commit that file, see CLAUDE.md):
#
#   ,,1 to 3,> 3 to 6,> 6 to 10,...
#   TG1,T,"±0,007","±0,012","±0,018",...
#   TG1,NT,"±0,012","±0,018","±0,022",...
#   TG9,,"±0,30","±0,49","±0,75",...
#
# Row 1's first two cells are ignored (whatever they contain); every
# cell after that is a dimension-range header. Each data row's first
# cell is a group name, second is its type (T / NT / blank). A blank
# type means the standard doesn't distinguish tool vs non-tool at that
# class -- the one value is stored as *both* tool_value and
# non_tool_value, so the matrix UI's T/NT boxes both show a real number
# rather than one looking like missing data (confirmed with the user).
#
# Format 2 (see second_format.xlsx, shared for context only -- same
# never-commit rule): each "nominal size range" spans several rows, one
# per named accuracy grade, instead of format 1's T/NT pair --
#
#   ,,from 0,1 to 1,over 1 up to 3,over 3 up to 6,over 10
#   1  to 6,fine,"±0,05","±0,08","±0,1",–
#   ,medium,"±0,1","±0,15","±0,2",–
#   ,course,"±0,2","±0,3","±0,4",–
#   ,very course,"±0,5","±0,5","±0,8",–
#   2  to 10,fine,...
#
# Column A carries the nominal-size-range label only on the first row of
# each block (the source spreadsheet merges that cell vertically; saved
# as CSV, the merge becomes a blank cell on every row after the first)
# -- blank means "same range as the row above". Column B is a free-text
# grade name, not restricted to a fixed set of four -- every non-blank
# value in it is a distinct group. There is exactly one value per range
# cell (not a T/NT pair), stored the same way format 1 stores a
# blank-type row: as both tool_value and non_tool_value. The top range
# may be open-ended ("over 10", no upper bound) -- see
# models/dimension_range.py's nullable max_value.
#
# Format 2's real header can sit on row 1 directly (a hand-built file
# with no title row) or row 2 (second_format.xlsx has a decorative
# merged title -- "Material Tickness" -- spanning the value columns
# above it) -- see _find_v2_header.
#
# Every problem found is collected into `errors` rather than raising on
# the first one -- a failed import should report everything wrong with
# the file in one pass, not one fix-and-reupload cycle at a time. If
# `errors` is non-empty, the caller must not create anything: we don't
# invent values, and we don't half-import a table either.

import csv
import io
from dataclasses import dataclass, field

# Comfortably covers any realistic tolerance table -- checked by the API
# layer against the raw upload before this module ever sees the text.
MAX_IMPORT_BYTES = 2 * 1024 * 1024

# Matches the "blank cell = no row, not a stored zero" rule the hand-edit
# endpoint already follows (set_tolerance_value_cell in api/reference_data.py).
# Hyphen, en dash, em dash -- all seen used as "no value" in real tables.
_BLANK_MARKERS = {"", "-", "–", "—"}

_VALID_TYPES = {"T", "NT", ""}


@dataclass
class ParsedRange:
    label: str
    min_value: float
    # None for an open-ended top range ("over 10", no upper bound) --
    # only format 2 ever produces this.
    max_value: float | None


@dataclass
class ParsedGroupRow:
    name: str
    # Range position (index into ParseResult.ranges) -> value.
    tool_values: dict[int, float] = field(default_factory=dict)
    non_tool_values: dict[int, float] = field(default_factory=dict)


@dataclass
class ParseResult:
    ranges: list[ParsedRange]
    groups: list[ParsedGroupRow]
    errors: list[str]


def _parse_range_label(label: str) -> tuple[float, float] | None:
    """"1 to 3" or "> 3 to 6" -> (1.0, 3.0) / (3.0, 6.0). None if it doesn't match."""
    text = label.strip()
    if text.startswith(">"):
        text = text[1:].strip()
    parts = text.split(" to ")
    if len(parts) != 2:
        return None
    try:
        min_value = float(parts[0].strip().replace(",", "."))
        max_value = float(parts[1].strip().replace(",", "."))
    except ValueError:
        return None
    return min_value, max_value


def _parse_range_label_v2(label: str) -> tuple[float, float | None] | None:
    """Format 2's looser phrasing: "from 0,1 to 1", "over 1 up to 3",
    and open-ended "over 10" (no upper bound) -> (10.0, None). Also
    accepts format 1's plain "1 to 3" / "> 3 to 6", so a file mixing
    conventions still parses. None if nothing matches.
    """
    text = label.strip().lower()
    if not text:
        return None
    if text.startswith("from "):
        text = text[5:].strip()
    open_ended = False
    if text.startswith("over "):
        text = text[5:].strip()
        open_ended = True  # unless a "to"/"up to" bound follows below
    text = text.replace("up to", "to")
    if text.startswith(">"):
        text = text[1:].strip()
    parts = text.split(" to ")
    try:
        if len(parts) == 1:
            if not open_ended:
                return None
            return float(parts[0].strip().replace(",", ".")), None
        if len(parts) == 2:
            min_value = float(parts[0].strip().replace(",", "."))
            max_value = float(parts[1].strip().replace(",", "."))
            return min_value, max_value
    except ValueError:
        return None
    return None


def _parse_value(raw: str) -> tuple[float | None, str | None]:
    """(value, error). value is None for a recognised blank marker; error
    is set if the text is neither blank nor a valid non-negative number."""
    text = raw.strip()
    if text in _BLANK_MARKERS:
        return None, None
    if text.startswith("±"):  # "±" -- optional, accepted either way
        text = text[1:].strip()
    text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None, f'"{raw}" is not a recognised number or blank marker'
    if value < 0:
        return None, f'"{raw}" must be given as a positive magnitude'
    return value, None


def _parse_v1_header(header: list[str]) -> tuple[list[ParsedRange], list[str]]:
    if len(header) < 3:
        return [], ["Row 1: expected at least one dimension-range column after the group and type columns."]

    ranges: list[ParsedRange] = []
    header_errors: list[str] = []
    for col_index, label in enumerate(header[2:], start=3):  # 1-based, for humans
        parsed = _parse_range_label(label)
        if parsed is None:
            header_errors.append(
                f'Row 1, column {col_index}: "{label}" isn\'t a range like "1 to 3" or "> 3 to 6".'
            )
            continue
        min_value, max_value = parsed
        if max_value <= min_value:
            header_errors.append(
                f'Row 1, column {col_index}: "{label}" -- the upper bound must be greater than the lower bound.'
            )
            continue
        ranges.append(ParsedRange(label=label.strip(), min_value=min_value, max_value=max_value))

    if not header_errors and not ranges:
        header_errors = ["Row 1: no dimension-range columns found."]
    return ranges, header_errors


def _parse_v1_data(all_rows: list[list[str]], ranges: list[ParsedRange]) -> ParseResult:
    errors: list[str] = []
    groups_by_name: dict[str, ParsedGroupRow] = {}
    group_order: list[str] = []
    seen_types_by_group: dict[str, set[str]] = {}

    for row_index, row in enumerate(all_rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue  # blank line -- skip silently, not an error

        if len(row) < 2:
            errors.append(f"Row {row_index}: expected a group name and a type column.")
            continue

        name = row[0].strip()
        type_field = row[1].strip().upper()
        if not name:
            errors.append(f"Row {row_index}: group name is blank.")
            continue
        if type_field not in _VALID_TYPES:
            errors.append(f'Row {row_index}: type "{row[1]}" must be "T", "NT", or blank.')
            continue

        seen = seen_types_by_group.setdefault(name, set())
        if type_field in seen:
            errors.append(f'Row {row_index}: group "{name}" already has a "{type_field or "(blank)"}" row.')
            continue
        if seen and (type_field == "" or "" in seen):
            # A blank-type row can't coexist with a T/NT row for the same
            # group -- ambiguous which one the group's untyped value means.
            errors.append(
                f'Row {row_index}: group "{name}" mixes a blank-type row with a T/NT row -- pick one style.'
            )
            continue
        seen.add(type_field)

        if name not in groups_by_name:
            groups_by_name[name] = ParsedGroupRow(name=name)
            group_order.append(name)
        group_row = groups_by_name[name]

        values = row[2:]
        for range_position in range(len(ranges)):
            if range_position >= len(values):
                continue  # short row -- a missing trailing cell is just blank
            raw = values[range_position]
            value, value_error = _parse_value(raw)
            if value_error:
                errors.append(f"Row {row_index}, column {range_position + 3}: {value_error}")
                continue
            if value is None:
                continue
            if type_field in ("T", ""):
                group_row.tool_values[range_position] = value
            if type_field in ("NT", ""):
                group_row.non_tool_values[range_position] = value

    if errors:
        return ParseResult(ranges=ranges, groups=[], errors=errors)
    if not group_order:
        return ParseResult(ranges=ranges, groups=[], errors=["No group rows found."])

    return ParseResult(ranges=ranges, groups=[groups_by_name[name] for name in group_order], errors=[])


def _find_v2_header(all_rows: list[list[str]]) -> tuple[int, list[ParsedRange]] | None:
    """Look for a fully-valid format-2 header on row 1, then row 2.

    Row 2 is tried second because second_format.xlsx has a decorative
    merged title row ("Material Tickness") spanning the value columns
    above the real header -- once saved as CSV that title survives only
    in its own top-left cell, with the rest of row 1 blank, so it always
    fails the "every column parses as a range" check below and row 2 is
    where the real header is. A hand-built file with no title row has
    its header on row 1 and is found there directly.
    """
    for row_index in (0, 1):
        if row_index >= len(all_rows):
            break
        header = all_rows[row_index]
        if len(header) < 3:
            continue
        ranges: list[ParsedRange] = []
        ok = True
        for label in header[2:]:
            parsed = _parse_range_label_v2(label)
            if parsed is None:
                ok = False
                break
            min_value, max_value = parsed
            if max_value is not None and max_value <= min_value:
                ok = False
                break
            ranges.append(ParsedRange(label=label.strip(), min_value=min_value, max_value=max_value))
        if ok and ranges:
            return row_index, ranges
    return None


def _parse_v2_data(
    all_rows: list[list[str]], header_row_idx: int, ranges: list[ParsedRange]
) -> ParseResult:
    errors: list[str] = []
    groups_by_name: dict[str, ParsedGroupRow] = {}
    group_order: list[str] = []
    seen_pairs: set[tuple[str, str]] = set()
    current_label: str | None = None

    for row_index, row in enumerate(all_rows[header_row_idx + 1 :], start=header_row_idx + 2):
        if not any(cell.strip() for cell in row):
            continue  # blank line -- skip silently, same as format 1

        if len(row) < 2:
            errors.append(f"Row {row_index}: expected a size-range label and an accuracy-grade column.")
            continue

        label = row[0].strip()
        if label:
            current_label = label
        elif current_label is None:
            errors.append(f"Row {row_index}: expected a size-range label in the first column.")
            continue

        grade = row[1].strip()
        if not grade:
            errors.append(f"Row {row_index}: accuracy-grade column is blank.")
            continue

        pair_key = (current_label, grade.lower())
        if pair_key in seen_pairs:
            errors.append(f'Row {row_index}: "{current_label}" already has a "{grade}" row.')
            continue
        seen_pairs.add(pair_key)

        name = f"{current_label} - {grade}"
        group_row = ParsedGroupRow(name=name)
        group_order.append(name)
        groups_by_name[name] = group_row

        values = row[2:]
        for range_position in range(len(ranges)):
            if range_position >= len(values):
                continue  # short row -- a missing trailing cell is just blank
            raw = values[range_position]
            value, value_error = _parse_value(raw)
            if value_error:
                errors.append(f"Row {row_index}, column {range_position + 3}: {value_error}")
                continue
            if value is None:
                continue
            # One value per cell in this format, not a T/NT pair -- store
            # as both, same convention as format 1's blank-type row (a
            # group the standard doesn't split by tooling).
            group_row.tool_values[range_position] = value
            group_row.non_tool_values[range_position] = value

    if errors:
        return ParseResult(ranges=ranges, groups=[], errors=errors)
    if not group_order:
        return ParseResult(ranges=ranges, groups=[], errors=["No group rows found."])

    return ParseResult(ranges=ranges, groups=[groups_by_name[name] for name in group_order], errors=[])


def parse_tolerance_csv(text: str) -> ParseResult:
    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        return ParseResult(ranges=[], groups=[], errors=["The file is empty."])

    v1_ranges, v1_header_errors = _parse_v1_header(all_rows[0])
    if not v1_header_errors:
        return _parse_v1_data(all_rows, v1_ranges)

    # Row 1 doesn't parse as format 1's header -- before reporting those
    # errors, check whether this is actually a format-2 file rather than
    # a broken format-1 one. This only takes over when a genuinely valid
    # format-2 header is found; a file that matches neither format still
    # gets the original format-1 errors below, since that remains the
    # more common/expected shape and its wording is what existing users
    # (and tests) already rely on.
    v2_match = _find_v2_header(all_rows)
    if v2_match is not None:
        header_row_idx, v2_ranges = v2_match
        return _parse_v2_data(all_rows, header_row_idx, v2_ranges)

    return ParseResult(ranges=[], groups=[], errors=v1_header_errors)
