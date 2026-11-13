import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sentry_sdk
from typesafe_sdk import TypeSafeClient, Noul
from factory import config
from factory.questions import QUESTIONS, decide

CASES = {
    'swallowed_exception': [
        ('cut', 'Parse a required integer; invalid text must raise.', 'except ValueError:\n        return 0', 'def parse(text):\n    try:\n        return int(text)\n    except ValueError:\n        return 0'),
        ('cut', 'Persist the order and propagate storage errors.', 'except OSError:\n        pass', 'def save(order, store):\n    try:\n        store.write(order)\n    except OSError:\n        pass'),
        ('cut', 'Load every required record; missing IDs are errors.', 'except KeyError:\n            continue', 'def load(ids, records):\n    result = []\n    for key in ids:\n        try:\n            result.append(records[key])\n        except KeyError:\n            continue\n    return result'),
        ('keep', 'Use zero when the optional count is malformed.', 'except ValueError:\n        return 0', 'def count(text):\n    try:\n        return int(text)\n    except ValueError:\n        return 0'),
        ('keep', 'Report storage failures to the caller.', 'except OSError:\n        raise', 'def save(order, store):\n    try:\n        store.write(order)\n    except OSError:\n        raise'),
        ('keep', 'Return (success, value); callers check success.', 'except ValueError:\n        return False, None', 'def parse(text):\n    try:\n        return True, int(text)\n    except ValueError:\n        return False, None'),
    ],
    'restating_comment': [
        ('cut', 'Return the item count.', '# Return the length\n    return len(items)', 'def count(items):\n    # Return the length\n    return len(items)'),
        ('cut', 'Sort names alphabetically.', '# Sort names\n    names.sort()', 'def sort_names(names):\n    # Sort names\n    names.sort()\n    return names'),
        ('cut', 'Increment a counter.', '# Add one\n    counter += 1', 'def increment(counter):\n    # Add one\n    counter += 1\n    return counter'),
        ('keep', 'Compute the protocol payload length.', '# The trailing byte is the protocol checksum.\n    return len(payload) - 1', 'def size(payload):\n    # The trailing byte is the protocol checksum.\n    return len(payload) - 1'),
        ('keep', 'Produce stable export ordering.', '# Stable ordering keeps signed exports reproducible.\n    names.sort()', 'def export(names):\n    # Stable ordering keeps signed exports reproducible.\n    names.sort()\n    return names'),
        ('keep', 'Convert an index for the external API.', '# The external API uses one-based positions.\n    index += 1', 'def position(index):\n    # The external API uses one-based positions.\n    index += 1\n    return index'),
    ],
    'redundant_guard': [
        ('cut', 'Return a list copy of the supplied list.', 'if items is None:\n        return []', 'def copy(items):\n    items = list(items)\n    if items is None:\n        return []\n    return items'),
        ('cut', 'Return the absolute value of an integer.', 'if value is None:\n        return 0', 'def magnitude(value):\n    value = abs(value)\n    if value is None:\n        return 0\n    return value'),
        ('cut', 'Return the count of entries in a list.', 'if len(items) < 0:\n        return 0', 'def count(items):\n    if len(items) < 0:\n        return 0\n    return len(items)'),
        ('keep', 'Return the first item, or None for an empty list.', 'if not items:\n        return None', 'def first(items):\n    if not items:\n        return None\n    return items[0]'),
        ('keep', 'Return the average; empty input has average zero.', 'if not values:\n        return 0', 'def average(values):\n    if not values:\n        return 0\n    return sum(values) / len(values)'),
        ('keep', 'Reject negative ages with ValueError.', 'if age < 0:\n        raise ValueError("negative age")', 'def normalize(age):\n    if age < 0:\n        raise ValueError("negative age")\n    return int(age)'),
    ],
    'debug_print': [
        ('cut', 'Return the sum without writing output.', 'print(values)', 'def total(values):\n    print(values)\n    return sum(values)'),
        ('cut', 'Return a normalized name without console output.', 'print("entered normalize")', 'def normalize(name):\n    print("entered normalize")\n    return name.strip()'),
        ('cut', 'Return the fetched record; keep stdout silent.', 'print("record:", record)', 'def fetch(key, records):\n    record = records[key]\n    print("record:", record)\n    return record'),
        ('keep', 'Print the sum to the console.', 'print(sum(values))', 'def show_total(values):\n    print(sum(values))'),
        ('keep', 'Show a progress message before importing records.', 'print("Importing records")', 'def import_records(records, store):\n    print("Importing records")\n    store.write(records)'),
        ('keep', 'Print each record for the command-line inspect command.', 'print("record:", record)', 'def inspect(records):\n    for record in records:\n        print("record:", record)'),
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='before')
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    out = config.ROOT / 'data' / 'probe' / args.label
    out.mkdir(parents=True, exist_ok=False)
    model = config.env('JEV_MODEL')
    if not model:
        raise RuntimeError('JEV_MODEL must be set')
    client = TypeSafeClient()
    totals = {kind: dict(correct=0, wrong=0, unsettled=0, errors=0) for kind in QUESTIONS}
    for kind, cases in CASES.items():
        for index, (expected, ticket, snippet, function) in enumerate(cases):
            name = f'{kind}-{index + 1}'
            payload = dict(model=model, state=dict(ticket=ticket, snippet=snippet, function=function), questions={k: q.model_dump(mode='json', exclude_none=True) for k, q in QUESTIONS[kind].items()})
            if args.replay:
                payload = json.loads((args.replay / f'{name}.request.json').read_text())
            (out / f'{name}.request.json').write_text(json.dumps(payload, indent=2))
            started = time.perf_counter()
            try:
                with sentry_sdk.start_span(op='gen_ai.chat', name=f'jev probe {kind}'):
                    response = client.system_one(model=payload['model'], state=payload['state'], questions={k: Noul.model_validate(q) for k, q in payload['questions'].items()})
                probs = {k: a.noul for k, a in response.answers.items()}
                verdict = decide(kind, probs)
                outcome = 'unsettled' if verdict is None else 'correct' if verdict == expected else 'wrong'
                result = dict(expected=expected, verdict=verdict, probs=probs, outcome=outcome, latency_ms=(time.perf_counter()-started)*1000, response=response.model_dump(mode='json'))
            except Exception as exc:
                outcome = 'errors'
                result = dict(error=type(exc).__name__, message=str(exc))
            totals[kind][outcome] += 1
            (out / f'{name}.result.json').write_text(json.dumps(result, indent=2))
            print(name, json.dumps({k: v for k, v in result.items() if k != 'response'}), flush=True)
    (out / 'summary.json').write_text(json.dumps(totals, indent=2))
    print(json.dumps(totals, indent=2))


if __name__ == '__main__':
    main()
