"""Find slop candidates in agent-written Python and apply the matching fix.

Code decides WHAT a candidate is (structure). Models only judge WHETHER it is slop.
"""
import ast
import io
import tokenize
from dataclasses import dataclass


@dataclass
class Candidate:
    kind: str          # swallowed_exception | restating_comment | redundant_guard | debug_print
    start: int         # 1-based, inclusive
    end: int
    snippet: str
    function: str      # enclosing function source, for context

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.snippet.strip()}"


FIX_DESCRIPTION = {
    "swallowed_exception": "remove the try/except and keep only the try body",
    "restating_comment": "delete the comment",
    "redundant_guard": "delete the if-check",
    "debug_print": "delete the print call",
}


def _lines(src: str, start: int, end: int) -> str:
    return "\n".join(src.splitlines()[start - 1:end])


def _enclosing(tree: ast.Module, src: str, line: int) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= node.end_lineno:
            return ast.get_source_segment(src, node) or ""
    return src[:3000]


def _swallows(node: ast.Try) -> bool:
    return not node.orelse and not node.finalbody and not any(
        isinstance(n, ast.Raise) for h in node.handlers for n in ast.walk(h)
    )


def _is_guard(node: ast.If) -> bool:
    return not node.orelse and len(node.body) == 1 and isinstance(node.body[0], (ast.Raise, ast.Return))


def _is_print(node: ast.AST) -> bool:
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "print")


def extract(src: str) -> list[Candidate]:
    tree = ast.parse(src)
    out: list[Candidate] = []
    for node in ast.walk(tree):
        kind = None
        if isinstance(node, ast.Try) and _swallows(node):
            kind = "swallowed_exception"
        elif isinstance(node, ast.If) and _is_guard(node):
            kind = "redundant_guard"
        elif _is_print(node):
            kind = "debug_print"
        if kind:
            out.append(Candidate(kind, node.lineno, node.end_lineno, _lines(src, node.lineno, node.end_lineno),
                                 _enclosing(tree, src, node.lineno)))

    # Full-line comment blocks; snippet includes the next code line so a reader can compare.
    lines = src.splitlines()
    comment_lines = sorted({
        tok.start[0] for tok in tokenize.generate_tokens(io.StringIO(src).readline)
        if tok.type == tokenize.COMMENT and lines[tok.start[0] - 1].lstrip().startswith("#")
    })
    blocks: list[list[int]] = []
    for ln in comment_lines:
        if blocks and ln == blocks[-1][-1] + 1:
            blocks[-1].append(ln)
        else:
            blocks.append([ln])
    for b in blocks:
        nxt = next((i for i in range(b[-1] + 1, len(lines) + 1) if lines[i - 1].strip()), b[-1])
        out.append(Candidate("restating_comment", b[0], b[-1], _lines(src, b[0], nxt),
                             _enclosing(tree, src, b[0])))
    return sorted(out, key=lambda c: c.start)


def apply_fix(src: str, c: Candidate) -> str | None:
    """Return the source with this candidate fixed, or None if the fix can't be applied cleanly."""
    lines = src.splitlines()
    if c.kind == "swallowed_exception":
        node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Try) and n.lineno == c.start)
        body = lines[c.start: node.body[-1].end_lineno]  # everything after 'try:', incl. comments
        indent = len(lines[c.start - 1]) - len(lines[c.start - 1].lstrip())
        first = lines[node.body[0].lineno - 1]
        extra = len(first) - len(first.lstrip()) - indent
        body = [b[extra:] if b[:extra].strip() == "" else b for b in body]
        new = lines[:c.start - 1] + body + lines[c.end:]
    else:
        new = lines[:c.start - 1] + lines[c.end:]
    for candidate in (new, lines[:c.start - 1] + [" " * (len(lines[c.start - 1]) - len(lines[c.start - 1].lstrip())) + "pass"] + lines[c.end:]):
        text = "\n".join(candidate) + "\n"
        try:
            ast.parse(text)
            return text
        except SyntaxError:
            continue
    return None
