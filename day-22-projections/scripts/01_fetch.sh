#!/usr/bin/env bash
# Day 22 · Projections, step 1: install the JS dependencies and fetch the Blue Marble texture.
#
# Natural Earth boundaries come with the world-atlas npm package (installed here).
# The Blue Marble texture is NASA's (public domain); the copy used here is the
# 4096 x 2048 equirectangular JPEG that ships in the three-globe npm package,
# because npm is reachable from every machine this was built on.
#
# Output: $D22_WORK/bluemarble.jpg (default ../../../work/day-22-projections)
set -euo pipefail
cd "$(dirname "$0")"

WORK="${D22_WORK:-../../../work/day-22-projections}"
mkdir -p "$WORK"

npm install --no-audit --no-fund

# Pull only the texture out of the three-globe tarball.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
( cd "$TMP" && npm pack three-globe@2.45.6 --silent >/dev/null && tar xzf three-globe-*.tgz package/example/img/earth-blue-marble.jpg )
cp "$TMP/package/example/img/earth-blue-marble.jpg" "$WORK/bluemarble.jpg"
echo "wrote $WORK/bluemarble.jpg"
