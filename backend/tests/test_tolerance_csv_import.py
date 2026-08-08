# Tests for the tolerance-table CSV parser (app/core/tolerance_csv_import.py).
#
# No fixtures needed -- the module deliberately has no DB or FastAPI
# imports, so these are plain function calls against literal CSV text.

import pytest

from app.core.tolerance_csv_import import parse_tolerance_csv

# Shape of the real example file (tolerance_table_EXAMPLE.csv), but with
# placeholder numbers -- that file's actual tolerance-standard figures
# are shared for context only and never appear in this repo (see CLAUDE.md).
TOLERANCE_TABLE_CSV = (
    ',,1 to 3,> 3 to 6,> 6 to 10\n'
    'TG1,T,"±0,10","±0,20","±0,30"\n'
    'TG1,NT,"±0,20","±0,30",–\n'
    'TG2,,"±0,50","±0,60","±0,70"\n'
)


def test_tolerance_table_file_parses_cleanly():
    result = parse_tolerance_csv(TOLERANCE_TABLE_CSV)
    assert result.errors == []
    assert [r.label for r in result.ranges] == ["1 to 3", "> 3 to 6", "> 6 to 10"]
    assert [(r.min_value, r.max_value) for r in result.ranges] == [(1, 3), (3, 6), (6, 10)]
    assert [g.name for g in result.groups] == ["TG1", "TG2"]


def test_comma_decimal_and_leading_plus_minus_are_stripped():
    result = parse_tolerance_csv(TOLERANCE_TABLE_CSV)
    tg1 = result.groups[0]
    assert tg1.tool_values[0] == pytest.approx(0.10)
    assert tg1.tool_values[1] == pytest.approx(0.20)
    assert tg1.tool_values[2] == pytest.approx(0.30)


def test_blank_marker_leaves_no_entry_for_that_cell():
    result = parse_tolerance_csv(TOLERANCE_TABLE_CSV)
    tg1_non_tool = result.groups[0].non_tool_values
    assert 2 not in tg1_non_tool  # "> 6 to 10" was "-" for TG1/NT
    assert tg1_non_tool[0] == pytest.approx(0.20)


def test_blank_type_row_populates_both_tool_and_non_tool():
    result = parse_tolerance_csv(TOLERANCE_TABLE_CSV)
    tg2 = result.groups[1]
    assert tg2.tool_values[0] == pytest.approx(0.50)
    assert tg2.non_tool_values[0] == pytest.approx(0.50)
    assert tg2.tool_values == tg2.non_tool_values


def test_plain_point_decimal_and_no_plus_minus_also_parse():
    # A company's own custom standard, not shaped like the example at all.
    csv_text = ',,1 to 3,3 to 6\nTG1,T,0.5,1.25\nTG1,NT,0.6,1.5\n'
    result = parse_tolerance_csv(csv_text)
    assert result.errors == []
    assert result.groups[0].tool_values[0] == pytest.approx(0.5)
    assert result.groups[0].tool_values[1] == pytest.approx(1.25)


def test_arbitrary_group_and_range_count_not_hardcoded_to_a_fixed_shape():
    # 2 groups, 2 ranges -- proves nothing assumes a fixed 9x16 shape.
    csv_text = ',,0 to 1,1 to 2\nA,T,0.1,0.2\nB,,0.3,0.4\n'
    result = parse_tolerance_csv(csv_text)
    assert result.errors == []
    assert len(result.ranges) == 2
    assert len(result.groups) == 2


def test_bad_range_header_reports_specific_location():
    csv_text = ',,not a range\nTG1,T,0.1\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "Row 1, column 3" in result.errors[0]


def test_range_with_upper_bound_not_greater_than_lower_is_rejected():
    csv_text = ',,5 to 5\nTG1,T,0.1\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "upper bound" in result.errors[0]


def test_bad_type_value_reports_specific_row():
    csv_text = ',,1 to 3\nTG1,XX,0.1\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "Row 2" in result.errors[0]
    assert 'must be "T", "NT", or blank' in result.errors[0]


def test_duplicate_group_type_pair_is_rejected():
    csv_text = ',,1 to 3\nTG1,T,0.1\nTG1,T,0.2\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "already has" in result.errors[0]


def test_mixing_blank_type_with_typed_row_is_rejected():
    csv_text = ',,1 to 3\nTG1,,0.1\nTG1,T,0.2\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "mixes a blank-type row" in result.errors[0]


def test_negative_value_is_rejected():
    csv_text = ',,1 to 3\nTG1,T,-0.1\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "positive magnitude" in result.errors[0]


def test_unparseable_value_is_rejected():
    csv_text = ',,1 to 3\nTG1,T,banana\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "not a recognised number" in result.errors[0]


def test_multiple_problems_are_all_reported_in_one_pass():
    csv_text = ',,1 to 3\nTG1,XX,0.1\nTG2,T,banana\nTG3,T,-1\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 3


def test_blank_lines_are_skipped_without_shifting_row_numbers():
    csv_text = ',,1 to 3\n\nTG1,T,0.1\n\nTG2,XX,0.2\n'
    result = parse_tolerance_csv(csv_text)
    # TG2's bad type is on line 5, not line 4 -- blank lines must not
    # shift the reported row number.
    assert len(result.errors) == 1
    assert "Row 5" in result.errors[0]


def test_empty_file_is_rejected():
    result = parse_tolerance_csv("")
    assert result.errors == ["The file is empty."]


def test_no_range_columns_is_rejected():
    # Just the group and type columns, header has nothing after them.
    result = parse_tolerance_csv(",\nTG1,T\n")
    assert "at least one dimension-range column" in result.errors[0]


def test_no_group_rows_is_rejected():
    result = parse_tolerance_csv(",,1 to 3\n")
    assert result.errors == ["No group rows found."]


def test_valid_file_creates_nothing_partial_when_a_later_row_fails():
    # A file valid except for one bad cell near the end -- the whole
    # parse must fail, with no groups returned to create from.
    csv_text = ',,1 to 3\nTG1,T,0.1\nTG2,T,0.2\nTG3,T,banana\n'
    result = parse_tolerance_csv(csv_text)
    assert result.groups == []
    assert len(result.errors) == 1
