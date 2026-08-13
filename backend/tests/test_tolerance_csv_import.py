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


# --- format 2: accuracy-grade layout (see second_format.xlsx, shared for
# context only -- never commit that file, see CLAUDE.md) --------------
#
# Shape: each nominal size range spans several rows (one per named
# accuracy grade) instead of format 1's T/NT pair; column A carries the
# size-range label only on the block's first row (blank = "same as
# above", simulating the source spreadsheet's vertical merge once saved
# as CSV); the last range may be open-ended ("over N", no upper bound).

ACCURACY_GRADE_CSV = (
    ',,"from 0,1 to 1",over 1 up to 3,over 3 up to 6,over 10\n'
    '1  to 6,fine,"±0,05","±0,08","±0,1",–\n'
    ',medium,"±0,1","±0,15","±0,2",–\n'
    ',course,"±0,2","±0,3","±0,4",–\n'
    ',very course,"±0,5","±0,5","±0,8",–\n'
)


def test_accuracy_grade_file_parses_cleanly():
    result = parse_tolerance_csv(ACCURACY_GRADE_CSV)
    assert result.errors == []
    assert [g.name for g in result.groups] == [
        "1  to 6 - fine",
        "1  to 6 - medium",
        "1  to 6 - course",
        "1  to 6 - very course",
    ]


def test_accuracy_grade_open_ended_top_range_has_no_max():
    result = parse_tolerance_csv(ACCURACY_GRADE_CSV)
    assert result.ranges[-1].label == "over 10"
    assert result.ranges[-1].min_value == 10
    assert result.ranges[-1].max_value is None


def test_accuracy_grade_single_value_stored_as_both_tool_and_non_tool():
    # One value per cell in this format, not a T/NT pair -- reuses format
    # 1's blank-type-row convention (confirmed with the user).
    result = parse_tolerance_csv(ACCURACY_GRADE_CSV)
    fine = result.groups[0]
    assert fine.tool_values[0] == pytest.approx(0.05)
    assert fine.tool_values == fine.non_tool_values


def test_accuracy_grade_open_ended_cell_left_blank_has_no_entry():
    result = parse_tolerance_csv(ACCURACY_GRADE_CSV)
    fine = result.groups[0]
    assert 3 not in fine.tool_values  # "over 10" was "-" for every grade


def test_accuracy_grade_file_with_a_decorative_title_row_still_parses():
    # second_format.xlsx has a merged title ("Material Tickness") over
    # the value columns above the real header -- once saved as CSV that
    # survives only in its own top-left cell, with the rest of the row
    # blank. _find_v2_header must fall through to row 2 in that case.
    csv_text = ",,Material Tickness,,,\n" + ACCURACY_GRADE_CSV
    result = parse_tolerance_csv(csv_text)
    assert result.errors == []
    assert [g.name for g in result.groups] == [
        "1  to 6 - fine",
        "1  to 6 - medium",
        "1  to 6 - course",
        "1  to 6 - very course",
    ]


def test_accuracy_grade_duplicate_range_and_grade_pair_is_rejected():
    # Header uses "from ... to ..." specifically so it's rejected by
    # format 1's stricter grammar and the dispatcher takes the format-2
    # path -- a plain "1 to 3" header would (correctly) be treated as
    # format 1 instead, where column B means something else entirely.
    csv_text = ',,from 1 to 3\n1 to 6,fine,0.1\n,fine,0.2\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert '"1 to 6" already has a "fine" row' in result.errors[0]


def test_accuracy_grade_blank_grade_column_is_rejected():
    csv_text = ',,from 1 to 3\n1 to 6,,0.1\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "accuracy-grade column is blank" in result.errors[0]


def test_accuracy_grade_row_with_no_prior_label_is_rejected():
    # The very first data row has a blank size-range column, so there is
    # nothing to carry down from -- unlike every row after it.
    csv_text = ',,from 1 to 3\n,fine,0.1\n'
    result = parse_tolerance_csv(csv_text)
    assert len(result.errors) == 1
    assert "expected a size-range label" in result.errors[0]


def test_a_format_1_style_file_is_never_misdetected_as_format_2():
    # Regression guard for the dispatcher: a clean format-1 file must
    # take the format-1 path, not accidentally match format 2's looser
    # grammar (both "T"/"NT" happen to be short strings that could, in
    # principle, be mistaken for a grade name).
    result = parse_tolerance_csv(TOLERANCE_TABLE_CSV)
    assert [g.name for g in result.groups] == ["TG1", "TG2"]


def test_malformed_header_still_reports_the_original_format_1_error():
    # Neither of these matches format 2 either (no second header row, and
    # the same text doesn't validate as a format-2 header) -- the
    # dispatcher must fall through to exactly the original format-1
    # error, not a generic "doesn't match either format" message.
    result = parse_tolerance_csv(',,not a range\nTG1,T,0.1\n')
    assert len(result.errors) == 1
    assert "isn't a range like" in result.errors[0]

    result = parse_tolerance_csv(',,5 to 5\nTG1,T,0.1\n')
    assert len(result.errors) == 1
    assert "upper bound" in result.errors[0]
