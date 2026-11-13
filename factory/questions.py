"""All Jev question wording, criteria, and thresholds, plus the keep/cut truth table.

Jev gives judgments. This file decides. Edit wording here only.
"""
from typesafe_sdk import Noul, NoulCriteria

YES, NO = 0.7, 0.3  # Noul thresholds (TypeSafe's suggested defaults)

QUESTIONS = {
    "swallowed_exception": {
        "discards": Noul(
            instructions="Does the except block in `snippet` throw the error away so the caller never learns it happened?",
            criteria=NoulCriteria(
                true="The handler passes, continues, or returns None or a default value, and nothing tells the caller an error occurred",
                false="The handler logs the error, re-raises it, or returns a value the caller is meant to check as a failure",
            ),
        ),
        "ticket_wants_silence": Noul(
            instructions="Does `ticket` ask for errors to be ignored or replaced with a default value?",
            criteria=NoulCriteria(
                true="The ticket says to ignore failures, fall back to a default, or never raise",
                false="The ticket says to raise errors, or says nothing about ignoring them",
            ),
        ),
    },
    "restating_comment": {
        "restates": Noul(
            instructions="Does the comment in `snippet` only repeat what the line of code below it already says?",
            criteria=NoulCriteria(
                true="Like '# add one to i' above 'i += 1': the comment adds nothing a reader of the code would not already see",
                false="The comment explains why, states a constraint, or describes something not obvious from the code",
            ),
        ),
    },
    "redundant_guard": {
        "ticket_requires": Noul(
            instructions="Does `ticket` ask for the case that the if-check in `snippet` handles?",
            criteria=NoulCriteria(
                true="The ticket describes this input or error case, for example by saying to raise an error for it",
                false="The ticket never mentions this case",
            ),
        ),
        "function_relies": Noul(
            instructions="Would the rest of `function` break or return a wrong result if the if-check in `snippet` were deleted?",
            criteria=NoulCriteria(
                true="Later code depends on the check, for example it would divide by zero or index an empty list",
                false="Later code works the same for the inputs the check rejects, or those inputs cannot happen",
            ),
        ),
    },
    "debug_print": {
        "is_debug": Noul(
            instructions="Is the print call in `snippet` leftover debugging output?",
            criteria=NoulCriteria(
                true="It prints internal values or progress messages that `ticket` did not ask for",
                false="`ticket` asks for this output to be shown to the user",
            ),
        ),
    },
}


def decide(kind: str, p: dict[str, float]) -> str | None:
    """Truth table. Returns 'cut', 'keep', or None (unsettled -> escalate to System 2)."""
    if kind == "swallowed_exception":
        if p["ticket_wants_silence"] > YES or p["discards"] < NO:
            return "keep"
        if p["discards"] > YES and p["ticket_wants_silence"] < NO:
            return "cut"
    elif kind == "restating_comment":
        if p["restates"] > YES:
            return "cut"
        if p["restates"] < NO:
            return "keep"
    elif kind == "redundant_guard":
        if p["ticket_requires"] > YES or p["function_relies"] > YES:
            return "keep"
        if p["ticket_requires"] < NO and p["function_relies"] < NO:
            return "cut"
    elif kind == "debug_print":
        if p["is_debug"] > YES:
            return "cut"
        if p["is_debug"] < NO:
            return "keep"
    return None
