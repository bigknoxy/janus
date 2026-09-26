#!/usr/bin/env python3
"""Mine janus's own git history into real-fix eval fixtures.

The SWE-bench trick at home scale: every merged fix commit is a
bug→fix pair with a real prompt (the message) and a real oracle (the
tests the fix made pass). For each candidate commit:

  buggy_files  = source files as of the PARENT rev
  tests        = the test file(s) the commit touched (as of commit HEAD)
  prompt       = cleaned commit subject
  validity     = tests FAIL on parent content and PASS at HEAD
                 (the only honest fixture criteria)

Corpus lands in eval_corpus/history/. Deduplicates by sha, so it's safe
to re-run after every merge — benchmarks grow themselves.

    python dev/mine_history.py [--repo .] [--since v0.1.0]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def sh(args: list[str], cwd: Path) -> str:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def commits(repo: Path, since: str | None) -> list[tuple[str, str, str]]:
    rng = f"{since}..HEAD" if since else "HEAD"
    out = sh(["git", "log", "--first-parent", rng, "--format=%H%x00%P%x00%s"], repo)
    rows = []
    for line in out.splitlines():
        if not line:
            continue
        h, parents, subject = line.split("\x00", 2)
        parent = parents.split()[0] if parents else ""
        rows.append((h, parent, subject))
    return rows


def looks_like_fix(subject: str) -> bool:
    head = re.match(r"(?i)^(fix|feat.*safe|feat.*guard|repair)", subject)
    return bool(head) or "fix" in subject.lower()


def mine_commit(repo: Path, sha: str, parent: str) -> dict | None:
    if not parent:
        return None
    diff_files = sh(["git", "diff-tree", "--no-commit-id", "--name-status", "-r", sha], repo)
    src_files, test_files = [], []
    for line in diff_files.splitlines():
        status, _, path = line.partition("\t")
        if not path.endswith(".py"):
            continue
        if path.startswith("tests/"):
            test_files.append(path)
        elif path.startswith("src/"):
            src_files.append(path)
    if not src_files or not test_files or len(src_files) > 2 or len(test_files) > 2:
        return None

    files: dict[str, str] = {}
    # Full parent source tree: mined tests import the package, not one file.
    all_src = sh(["git", "ls-tree", "-r", "--name-only", parent, "src/"], repo)
    for f in all_src.splitlines():
        if f.endswith(".py"):
            files[f] = sh(["git", "show", f"{parent}:{f}"], repo) + "\n"
    tests: dict[str, str] = {}
    for f in test_files:
        fixed = sh(["git", "show", f"{sha}:{f}"], repo)
        if fixed:
            tests[f] = fixed + "\n"
    if not tests:
        return None
    # Support files tests need (marker constants etc.): pull tests/__init__
    init = sh(["git", "show", f"{parent}:tests/__init__.py"], repo)
    files["tests/__init__.py"] = init or ""
    return {"src": src_files, "tests": test_files, "files": files, "test_files": tests}


def validate(files: dict[str, str], tests: dict[str, str]) -> bool:
    """Red on the buggy inputs, and at least one test present that could
    flip (we don't assert green-on-HEAD here — correctness of HEAD is the
    tree's business)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, c in {**files, **tests}.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(c)
        # minimal package shims
        for pkg in (root / "src").rglob("*"):
            if pkg.is_dir() and (pkg / "__init__.py").exists() is False:
                pass
        test_targets = [str(p.relative_to(root)) for p in root.rglob("test_*.py")]
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--import-mode=importlib", *test_targets],
            cwd=root, capture_output=True, text=True, timeout=180,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(root / "src")},
        )
        return r.returncode != 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=HERE)
    ap.add_argument("--since", default=None)
    args = ap.parse_args()
    out_dir = args.repo / "eval_corpus" / "history"
    out_dir.mkdir(parents=True, exist_ok=True)
    found = 0
    for sha, parent, subject in commits(args.repo, args.since):
        if not looks_like_fix(subject):
            continue
        if (out_dir / f"history_{sha[:7]}.json").exists():
            continue
        mined = mine_commit(args.repo, sha, parent)
        if not mined:
            continue
        if not validate(mined["files"], mined["test_files"]):
            continue
        fx = {
            "name": f"history_{sha[:7]}",
            "bug_class": "real-history",
            "origin": f"janus commit {sha[:7]} ({subject[:66]})",
            "prompt": subject,
            "files": mined["files"],
            "tests": mined["test_files"],
        }
        (out_dir / f"{fx['name']}.json").write_text(json.dumps(fx, indent=2))
        found += 1
        print(f"mined {fx['name']}: {subject[:60]}")
    print(f"history corpus: +{found} fixtures")


if __name__ == "__main__":
    main()
