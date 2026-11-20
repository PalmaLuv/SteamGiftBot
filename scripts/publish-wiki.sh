#!/usr/bin/env bash
# Publishes docs/wiki to the repository's GitHub wiki.
#
# The pages are written to work inside the repository (links end in .md,
# pictures sit in docs/images). On the wiki, links have no extension and the
# pictures and other files are fetched from the repository itself, so this
# rewrites them on the way.
#
#   REPO=PalmaLuv/SteamGiftBot   which repository's wiki
#   BRANCH=main                  branch the pictures and files are taken from
#   WIKI_REMOTE=...              git URL of the wiki (default: SSH to github.com)
#
# Needs write access to <repo>.wiki.git: an account SSH key or token. Deploy
# keys do not reach wikis. The wiki must exist: create its first page once on
# GitHub (Wiki → Create the first page).
set -euo pipefail
cd "$(dirname "$0")/.."

REPO="${REPO:-PalmaLuv/SteamGiftBot}"
BRANCH="${BRANCH:-main}"
WIKI_REMOTE="${WIKI_REMOTE:-git@github.com:${REPO}.wiki.git}"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
BLOB="https://github.com/${REPO}/blob/${BRANCH}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone --quiet --depth 1 "$WIKI_REMOTE" "$work/wiki"
find "$work/wiki" -maxdepth 1 -name '*.md' -delete

for page in docs/wiki/*.md; do
  python3 - "$page" "$work/wiki/$(basename "$page")" "$RAW" "$BLOB" <<'EOF'
import re, sys
source, target, raw, blob = sys.argv[1:]
text = open(source, encoding='utf-8').read()
text = re.sub(r'\]\(\.\./images/([^)]+)\)', rf'](' + raw + r'/docs/images/\1)', text)
text = re.sub(r'\]\(\.\./\.\./([^)#]+)(#[^)]*)?\)', lambda m: f']({blob}/{m.group(1)}{m.group(2) or ""})', text)
text = re.sub(r'\]\(([^):/#]+)\.md(#[^)]*)?\)', lambda m: f']({m.group(1)}{m.group(2) or ""})', text)
open(target, 'w', encoding='utf-8').write(text)
EOF
done

cd "$work/wiki"
git add -A
if git diff --cached --quiet; then
  echo "Вики уже совпадает с docs/wiki."
  exit 0
fi
git commit --quiet -m "Update wiki from docs/wiki"
git push --quiet
echo "Опубликовано: https://github.com/${REPO}/wiki"
