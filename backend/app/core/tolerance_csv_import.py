# Parses a CSV export of a tolerance table (an industrial tolerance
# standard, or a company's own equivalent) into the shape
# api/reference_data.py needs to create a new ProcessType and its whole
# matrix in one go. Deliberately plain functions with no DB/FastAPI
# imports -- same testable-in-isolation convention as core/simulation.py
# and core/angled_simulation.py.
#
# Expected shape (see tolerance_table_EXAMPLE.csv, shared for context
# only -- never commit that file, see CLAUDE.md):
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
    max_value: float


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


def parse_tolerance_csv(text: str) -> ParseResult:
    all_rows = list(csv.reader(io.StringIO(text)))
    if not all_rows:
        return ParseResult(ranges=[], groups=[], errors=["The file is empty."])

    header = all_rows[0]
    if len(header) < 3:
        return ParseResult(
            ranges=[],
            groups=[],
            errors=["Row 1: expected at least one dimension-range column after the group and type columns."],
        )

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

    # A broken header makes column positions unreliable for every row
    # below it -- report the header problems and stop there rather than
    # guessing at data-row alignment.
    if header_errors:
        return ParseResult(ranges=[], groups=[], errors=header_errors)
    if not ranges:
        return ParseResult(ranges=[], groups=[], errors=["Row 1: no dimension-range columns found."])

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
