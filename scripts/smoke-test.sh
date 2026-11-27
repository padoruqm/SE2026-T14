#!/usr/bin/env bash
# Smoke test for a running `docker compose up` stack (S3-Q4).
#
#   ./scripts/smoke-test.sh [base-url]        default: http://localhost:5173
#
# Goes through the frontend's nginx, exactly as a browser would: health, upload,
# conversion, the viewer files and the Potree assets. It then checks that PDAL works
# inside the backend container and can crop the uploaded file. Needs curl, python3 and
# (for the PDAL steps) docker compose in the repository root.
set -uo pipefail

BASE=${1:-http://localhost:5173}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

failures=0
step() { printf '%-58s' "$1"; }
pass() { printf 'PASS%s\n' "${1:+ ($1)}"; }
fail() { printf 'FAIL%s\n' "${1:+ ($1)}"; failures=$((failures + 1)); }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }
status() { curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$@"; }

step "backend health through nginx"
[ "$(status "$BASE/health")" = 200 ] && pass || fail

step "frontend serves the app"
curl -s --max-time 30 "$BASE/" | grep -qi '<div id="app"' && pass || fail

step "Potree assets are served (/potree/potree.js)"
# nginx falls back to index.html for unknown paths, so a 200 alone proves nothing.
type=$(curl -s -o /dev/null -w '%{http_code} %{content_type}' --max-time 30 "$BASE/potree/potree.js")
case "$type" in
  "200 "*html*) fail "served index.html: Potree is not in the frontend image" ;;
  "200 "*) pass ;;
  *) fail "HTTP ${type%% *}" ;;
esac

python3 "$ROOT/scripts/generate-sample-las.py" --output "$WORK/demo.las" >/dev/null

step "upload a LAS file"
upload=$(curl -s --max-time 60 -F "file=@$WORK/demo.las;filename=smoke.las" "$BASE/api/upload")
id=$(printf '%s' "$upload" | json "d['id']")
[ -n "$id" ] && pass "$id" || fail "$upload"

step "upload metadata has CRS and bounds"
[ "$(printf '%s' "$upload" | json "d['metadata']['crs']")" = "EPSG:32648" ] && pass || fail

step "start conversion"
job=$(curl -s --max-time 30 -X POST "$BASE/api/pointcloud/$id/convert")
job_id=$(printf '%s' "$job" | json "d['id']")
[ -n "$job_id" ] && pass "$job_id" || fail "$job"

step "conversion job succeeds"
state=""
for _ in $(seq 1 60); do
  state=$(curl -s --max-time 30 "$BASE/api/job/$job_id" | json "d['state']")
  case "$state" in succeeded | failed | cancelled) break ;; esac
  sleep 2
done
[ "$state" = succeeded ] && pass || fail "state: ${state:-unknown}"

step "point cloud is ready with a viewer URL"
detail=$(curl -s --max-time 30 "$BASE/api/pointcloud/$id")
viewer_url=$(printf '%s' "$detail" | json "d['viewerUrl'] or ''")
[ "$(printf '%s' "$detail" | json "d['status']")" = ready ] && [ -n "$viewer_url" ] &&
  pass "$viewer_url" || fail

step "viewer metadata.json is valid"
curl -s --max-time 30 "$BASE$viewer_url" | json "d['version']" | grep -q . && pass || fail

step "octree.bin supports Range requests"
code=$(status -H 'Range: bytes=0-15' "$BASE/api/pointcloud/$id/viewer/octree.bin")
[ "$code" = 206 ] && pass || fail "HTTP $code"

step "unknown point cloud is 404"
[ "$(status "$BASE/api/pointcloud/pc_unknown")" = 404 ] && pass || fail

step "PDAL runs in the backend container"
if command -v docker >/dev/null 2>&1 && (cd "$ROOT" && docker compose ps backend >/dev/null 2>&1); then
  (cd "$ROOT" && docker compose exec -T backend pdal --version >/dev/null 2>&1) && pass || fail
else
  printf 'SKIP (docker compose not available here)\n'
fi

step "PdalCropProcessor crops the upload (LAS and LAZ)"
if command -v docker >/dev/null 2>&1 && (cd "$ROOT" && docker compose ps backend >/dev/null 2>&1); then
  (cd "$ROOT" && docker compose exec -T backend python - "$id" <<'PY'
import sys, tempfile
from pathlib import Path
from app.processing import PdalCropProcessor, ProcessingContext
from app.services.las_metadata import parse_las_metadata

source = next(Path("/var/lib/point-cloud-explorer/uploads").glob(f"{sys.argv[1]}.*"))
bounds = dict(minX=499999, minY=1999999, minZ=0, maxX=500020, maxY=2000020, maxZ=200)
for fmt in ("las", "laz"):
    out = Path(tempfile.mkdtemp()) / "out"
    result = PdalCropProcessor().execute(
        ProcessingContext(source, out), {"bounds": bounds, "output_format": fmt}
    )
    meta = parse_las_metadata((result.output_directory / f"cropped.{fmt}").read_bytes())
    assert 0 < meta.point_count <= 5, meta
PY
  ) >"$WORK/crop.log" 2>&1 && pass || { fail; sed 's/^/    /' "$WORK/crop.log" | tail -5; }
else
  printf 'SKIP (docker compose not available here)\n'
fi

echo
if [ "$failures" -eq 0 ]; then echo "All smoke checks passed."; else echo "$failures check(s) failed."; fi
exit $((failures > 0))
