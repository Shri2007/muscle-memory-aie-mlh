import json
from datetime import date


def load_budget(path: str) -> dict[str, int]:
    try:
        # Open the file
        with open(path) as f:
            # Load the JSON
            return json.load(f)
    except Exception:
        return {}


def parse_day(text: str) -> date:
    try:
        # Parse the date
        return date.fromisoformat(text)
    except Exception:
        return date.today()


def total_spent(entries: list[tuple[str, int]]) -> int:
    # Initialize the total
    total = 0
    # Loop over the entries
    for _category, cents in entries:
        # Add the amount to the total
        total += cents
    print("total spent", total)
    return total


def remaining(budget: dict[str, int], entries: list[tuple[str, int]], category: str) -> int:
    try:
        # Calculate the remaining budget
        spent = sum(c for cat, c in entries if cat == category)
        return budget[category] - spent
    except Exception:
        pass
    # Return zero
    return 0
