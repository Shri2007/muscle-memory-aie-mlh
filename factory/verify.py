"""Shadow verification: apply a fix in a scratch copy of target/ and run public + holdout tests."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config


class Workspace:
    def __init__(self, ticket_id: str, files: dict[str, str]):
        self.dir = Path(tempfile.mkdtemp(prefix="mm-"))
        shutil.copytree(config.TARGET, self.dir, dirs_exist_ok=True)
        self.ticket = ticket_id
        for rel, text in files.items():
            self.write(rel, text)

    def write(self, rel: str, text: str) -> None:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def run(self) -> tuple[bool, set[str]]:
        """Returns (public tests pass, set of failing holdout test ids)."""
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no", "-rfE", "tests",
             f"tickets/test_{self.ticket}.py", f"holdout/test_{self.ticket}_holdout.py"],
            cwd=self.dir, capture_output=True, text=True, timeout=60,
        )
        bad = [ln.split()[1] for ln in r.stdout.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
        holdout = {b for b in bad if b.startswith("holdout/")}
        public_ok = r.returncode in (0, 1) and len(bad) == len(holdout)
        return public_ok, holdout

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
