#!/usr/bin/env python3
"""Mine janus's own git history into single-concern eval fixtures.

v2 (2026-09-26): multi-concern commits like the P0 audit fix (traversal +
create-parity + bare-except narrowing) previously generated one giant
fixture too big for a 4B patch. Now: run every test node of the touched
test files against the PARENT tree; each failing node becomes its own
fixture with only that test function. One bug → one fixture → one patch.

Output: eval_corpus/history/history_<sha>_<testname>.json, deduped by name.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def sh(args: list[str], cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60).stdout.strip()


def looks_like_fix(subject: str) -> bool:
    head = re.match(r"(?i)^(fix|feat.*safe|feat.*guard|repair)", subject)
    return bool(head) or "fix" in subject.lower()


def tree_files(repo: Path, rev: str, prefix: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in sh(["git", "ls-tree", "-r", "--name-only", rev, prefix], repo).splitlines():
        if rel.endswith(".py"):
            out[rel] = sh(["git", "show", f"{rev}:{rel}"], repo)
    return out


def write_tree(root: Path, files: dict[str, str]) -> None:
    shim = "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))\n"
    (root / "conftest.py").write_text(shim)
    init = files.pop("tests/__init__.py", "")
    for rel, content in {**files, "tests/__init__.py": init}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def failing_nodes(root: Path, test_file: str) -> list[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    print(env.get("PATH"))
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--import-mode=importlib",
            test_file,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    nodes = [ln.strip() for ln in r.stdout.splitlines() if "::" in ln]
    return nodes


def node_fails(root: Path, node: str) -> bool:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--import-mode=importlib", node],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return r.returncode != 0


def extract_test(source: str, node: str) -> str:
    """Line-faithful slice: top-of-file imports/assigns + the requested
    class/function's original lines."""
    parts = node.split("::")
    cls_name = parts[1] if len(parts) == 3 else None
    fn_name = parts[-1]
    lines = source.splitlines()
    tree = ast.parse(source)
    keep: set[int] = set()
    for n in tree.body:
        # keep imports, module assigns, and module-level helper functions
        if isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign)):
            keep.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not n.name.startswith("test_") or (not cls_name and n.name == fn_name):
                keep.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
        elif isinstance(n, ast.ClassDef) and cls_name and n.name == cls_name:
            for sub in n.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name == fn_name or not sub.name.startswith("test_"):
                        for lno in range(n.lineno, n.body[0].lineno):
                            keep.add(lno)
                        keep.update(range(sub.lineno, (sub.end_lineno or sub.lineno) + 1))
                else:
                    keep.update(range(sub.lineno, (sub.end_lineno or sub.lineno) + 1))
    return "\n".join(ln for i, ln in enumerate(lines, 1) if i in keep)


def mine_commit(repo: Path, sha: str, parent: str, subject: str) -> list[dict]:
    if not parent:
        return []
    # first-parent diff: works for both fix commits and PR merge commits
    # (diff-tree -r on a merge commit returns nothing — that swallowed all
    # of click's PR-merged fixes during the JB-1 probe)
    diff_files = sh(["git", "diff", "--name-only", parent, sha], repo)
    src_files = [
        ln.split("\t")[-1]
        for ln in diff_files.splitlines()
        if ln.split("\t")[-1].startswith("src/") and ln.split("\t")[-1].endswith(".py")
    ]
    test_files = [
        ln.split("\t")[-1]
        for ln in diff_files.splitlines()
        if ln.split("\t")[-1].startswith("tests/") and ln.split("\t")[-1].endswith(".py")
    ]
    if not src_files or not test_files or len(src_files) > 3 or len(test_files) > 2:
        return []

    parent_tree = tree_files(repo, parent, "src/")
    shim_src = {
        "tests/__init__.py": tree_files(repo, parent, "tests/").get("tests/__init__.py", "")
    }
    parent_tree.update(shim_src)

    # whole-repo test tree at HEAD: tests may import siblings' helpers
    tree_files(repo, parent, "tests/")

    fixed_tests = tree_files(repo, sha, "tests/")
    file_names = ", ".join(Path(f).name for f in src_files)

    fixtures = []
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # materialize parent tree: parent tests fail; commit's tests added
        files = dict(parent_tree)
        for rel, content in fixed_tests.items():
            if rel not in files or files[rel] != content:
                files[rel] = content
        # include all tests as of fixed commit (import helpers intact)
        write_tree(root, files)
        nodes = []
        for tf in fixed_tests:
            # only tests the commit actually touched — the old guard
            # (tf not in parent_tree) was always true for test files, so
            # every repo test entered red-first validation; click's flaky
            # parametrized stress tests burned hours as load-noise "fixes"
            if tf in test_files:
                for node in failing_nodes(root, tf):
                    if node_fails(root, node):
                        nodes.append(node)
        for node in set(nodes):
            fname = node.split("::")[-1]
            test_file_key = node.split("::")[0]  # e.g. tests/test_x.py
            test_file_rel = (
                ("tests/" + test_file_key)
                if not test_file_key.startswith("tests/")
                else test_file_key
            )
            test_src = fixed_tests.get(test_file_rel) or list(fixed_tests.values())[0]
            try:
                content = extract_test(test_src, node) + "\n"
                ast.parse(content)
            except SyntaxError:
                content = test_src  # fallback: whole file
            # re-validate: the SLICE must compile and still be red on parent
            (root / test_file_rel).write_text(content)
            if not node_fails(root, node):
                continue
            fixtures.append(
                {
                    "name": f"history_{sha[:7]}_{fname}",
                    "bug_class": "real-history",
                    "origin": f"janus {sha[:7]} · {subject[:80]}",
                    "prompt": f"{subject}; fix files: {file_names}",
                    "files": parent_tree,
                    "tests": {test_file_rel: content},
                }
            )
    return fixtures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=HERE)
    ap.add_argument("--since", default=None)
    args = ap.parse_args()
    out_dir = args.repo / "eval_corpus" / "history"
    out_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    rng = f"{args.since}..HEAD" if args.since else "HEAD"
    for line in sh(
        ["git", "log", "--first-parent", rng, "--format=%H%x00%P%x00%s"], args.repo
    ).splitlines():
        if not line:
            continue
        sha, parents, subject = line.split("\x00", 2)
        parent = parents.split()[0] if parents else ""
        if not looks_like_fix(subject):
            continue
        for fx in mine_commit(args.repo, sha, parent, subject):
            dest = out_dir / f"{fx['name']}.json"
            if dest.exists():
                continue
            dest.write_text(json.dumps(fx, indent=2))
            added += 1
            print("mined", fx["name"])
    print(f"history corpus: +{added} fixtures (this run)")


if __name__ == "__main__":
    main()
