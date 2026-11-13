# Adopt the learned reflexes in your CI

1. Copy `rules/` from this repo into your repo. Each file is plain Semgrep YAML that Muscle Memory learned from verified decisions.
2. Copy `.github/workflows/slop-reflexes.yml` into your `.github/workflows/`.
3. Open a PR. The check runs every active rule on the Python files you changed and fails if a learned reflex matches.
4. The CI workflow skips rules marked `active: false` (demoted after an over-cut). A plain `semgrep --config rules/` does not.
5. Try it locally first: `semgrep --config rules/ --error examples/agent_slop.py`.

`examples/` is intentional slop for the demo, so the workflow never checks it.

## Proof

The two rules the factory learned in its first full run (`mm-restating_comment-v1`, `mm-swallowed_exception-v2`), run as-is on `agent_slop.py` (output abridged: Semgrep also prints "Blocking" markers and the rule message under every finding):

```
$ semgrep --config rules/ examples/agent_slop.py
┌─────────────────┐
│ 9 Code Findings │
└─────────────────┘
    examples/agent_slop.py
    ❯❱ rules.mm-restating_comment-v1
            7┆ # Open the file
            8┆ with open(path) as f:
            ⋮┆----------------------------------------
            9┆ # Load the JSON
           10┆ return json.load(f)
    ❯❱ rules.mm-swallowed_exception-v2
           11┆ except Exception:
           12┆     return {}
    ❯❱ rules.mm-restating_comment-v1
           17┆ # Parse the date
           18┆ return date.fromisoformat(text)
    ❯❱ rules.mm-swallowed_exception-v2
           19┆ except Exception:
           20┆     return date.today()
    ❯❱ rules.mm-restating_comment-v1
           24┆ # Initialize the total
           25┆ total = 0
            ⋮┆----------------------------------------
           26┆ # Loop over the entries
           27┆ for _category, cents in entries:
            ⋮┆----------------------------------------
           36┆ # Calculate the remaining budget
           37┆ spent = sum(c for cat, c in entries if cat == category)
            ⋮┆----------------------------------------
           41┆ # Return zero
           42┆ return 0
```

Not flagged:
- `except Exception: pass`. v2 matches only `return`/assignment fallbacks. It was rewritten after v1 cut the `return None` that ticket T11 requires.
- The `print`. No debug_print rule has been learned yet.
- Line 28, a 6-word comment. `restating_comment` only matches comments of 2 to 5 words.

The rules are narrow because each one had to match at least 80% of verified CUTs and no verified KEEP before it was saved (both rules here match 5/5 CUT).
