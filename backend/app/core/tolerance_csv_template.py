# Builds the blank .xlsx a user downloads before importing their own
# tolerance table (see core/tolerance_csv_import.py for the format this
# has to match, and CLAUDE.md for why this deliberately contains no real
# numbers -- a real industrial tolerance standard's actual figures were
# shared with this project for context only and must never be
# redistributed to end users).
#
# Generated on request rather than a static file checked into the repo:
# there's no way to hand-author a real .xlsx binary without a library,
# and generating it from the same understanding as the parser keeps the
# two from silently drifting apart if the expected format ever changes.

from io import BytesIO

from openpyxl import Workbook
from openpyxl.comments import Comment

_INSTRUCTIONS = (
    "Row 1: leave columns A and B alone, then add one column per "
    'dimension range, labelled like "1 to 3" or "> 3 to 6" -- add as '
    "many as your standard needs.\n\n"
    "Each row below: column A is a tolerance group name, column B is "
    'T, NT, or blank (blank means the one value applies to both -- use '
    "this for a class your standard doesn't split by tooling).\n\n"
    "Leave a cell blank where your standard has no value for that "
    "group/range -- don't enter 0.\n\n"
    "When done, save as CSV (not .xlsx) and upload that file."
)


def build_import_template() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Tolerance Data"

    sheet.append(["Group", "Type", "1 to 3", "> 3 to 6", "> 6 to 10"])
    # Example rows illustrating the T/NT pairing and the blank-type
    # style -- deliberately no values in any of them.
    sheet.append(["TG1", "T"])
    sheet.append(["TG1", "NT"])
    sheet.append(["TG2", ""])

    sheet["A1"].comment = Comment(_INSTRUCTIONS, "GapFlushRSS")

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
