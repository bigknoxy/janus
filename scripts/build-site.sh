#!/usr/bin/env bash
# Build the gh-pages site: explicit allowlist (never the whole repo —
# internal docs and dev harnesses stay off the public domain).
set -euo pipefail
rm -rf site
mkdir -p site/docs
cp index.html site/
cp README.md LICENSE site/
for f in docs/*.md; do cp "$f" site/docs/; done
echo "site built: $(find site -type f | wc -l) files"
