#!/usr/bin/env bash
# Download the pinned Potree release and copy the files the viewer needs into
# frontend/public/potree, where Vite serves them as static assets.
set -euo pipefail

version="1.8.2"
url="https://github.com/potree/potree/releases/download/${version}/Potree_${version}.zip"
sha256="c140a8bce0ce129de762fbc0fd3ba7c21120ffd36d423dd2755abb39f32aebe5"

root="$(cd "$(dirname "$0")/.." && pwd)"
target="$root/frontend/public/potree"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

curl --fail --location --silent --show-error "$url" --output "$work/potree.zip"
printf '%s  %s\n' "$sha256" "$work/potree.zip" | shasum -a 256 --check --quiet
unzip -q "$work/potree.zip" -d "$work"

release="$work/Potree_${version}"
build="$release/build/potree"
rm -rf "$target"
mkdir -p "$target/libs"
cp -R "$build/potree.js" "$build/potree.css" "$build/resources" "$build/workers" \
  "$build/lazylibs" "$release/LICENSE" "$target/"
# Globals that potree.js expects but does not bundle.
cp "$release/libs/jquery/jquery-3.1.1.min.js" "$release/libs/other/BinaryHeap.js" \
  "$release/libs/tween/tween.min.js" "$release/libs/proj4/proj4.js" "$target/libs/"

printf 'Potree %s copied to %s\n' "$version" "$target"
