#!/usr/bin/env python3
"""Mine EXTERNAL OSS repos' fix-history into janus eval fixtures (JB-1).

Objective: the public claim "fixes bugs from real histories" currently only
covers janus's own git. This extends the same single-concern machinery
(see dev/mine_history.py v2) to any Python repo with a pytest tree, writing
fixtures to eval_corpus/external/ tagged bug_class=real-external.

Read the full brief at LifeOS: BACKLOG/JB1-real-repo-corpus-mining.md;
its ISCs + falsifiers are the bar for closing the GitHub issue.

Usage:  dev/mine_external.py <https://github.com/org/repo> [--since <ref>]
Constraints: fixtures are validated red-first on the parent tree before
being emitted; a candidate repo that validates zero fixtures is a finding,
not a failure.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from mine_history import mine_commit, sh  # noqa: E402


def mine_repo(url: str, since: str | None, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    with tempfile.TemporaryDirectory() as d:
        clone = Path(d) / "repo"
        r = subprocess.run(
            ["git", "clone", "--quiet", url, str(clone)],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            print(f"clone failed: {r.stderr[:200]}")
            return 0
        repo_name = Path(url.rstrip("/")).stem
        # layout auto-detection: src-layout (click, requests) vs flat-package
        # (pydantic, rich) — the hardcoded src/ prefix filtered every fix in
        # flat repos before validation ever ran
        if (clone / "src").is_dir():
            pkg_prefix = "src/"
        elif (clone / repo_name).is_dir():
            pkg_prefix = f"{repo_name}/"
        else:
            pkg_prefix = "src/"
        rng = f"{since}..HEAD" if since else "--since='60 days ago'"
        log_cmd = ["git", "log", "--first-parent"]
        log_cmd += [rng] if since else ["--since=60 days ago"]
        log_cmd += ["--format=%H%x00%P%x00%s"]
        for line in sh(log_cmd, clone).splitlines():
            if not line:
                continue
            sha, parents, subject = line.split("\x00", 2)
            parent = parents.split()[0] if parents else ""
            head = subject.lower()
            if not (head.startswith(("fix", "bug", "patch")) or "fix" in head):
                continue
            for fx in mine_commit(clone, sha, parent, subject, pkg_prefix):
                fx["bug_class"] = "real-external"
                fx["origin"] = f"{repo_name}@{sha[:7]} · {subject[:80]}"
                dest = out_dir / f"{repo_name}_{fx['name']}.json"
                if dest.exists():
                    continue
                dest.write_text(json.dumps(fx, indent=2))
                added += 1
                print("mined", dest.name)
    print(f"{repo_name}: +{added} external fixture(s)")
    return added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--since", default=None)
    args = ap.parse_args()
    mine_repo(args.url, args.since, HERE / "eval_corpus" / "external")


if __name__ == "__main__":
    main()
