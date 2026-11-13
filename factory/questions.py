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
            instructions="Does the comment in `snippet` merely describe the operation visibly performed by the adjacent code?",
            criteria=NoulCriteria(
                true="The comment paraphrases the adjacent operation or names its action without adding a reason, constraint, or domain fact",
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
            instructions="Can removing the if-check in `snippet` change the behavior of `function` for an input that reaches that check?",
            criteria=NoulCriteria(
                true="An input can reach and satisfy the check, and removing it changes the result or allows an error in later code",
                false="The check cannot be satisfied after the preceding code has executed, or removing it leaves the result and errors unchanged",
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
