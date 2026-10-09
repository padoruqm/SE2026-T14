#!/usr/bin/env bash
set -euo pipefail

apply=false
if [ "${1:-}" = "--apply" ]; then
  apply=true
elif [ "$#" -ne 0 ]; then
  printf '%s\n' 'Usage: create-labels-and-milestones.sh [--apply]' >&2
  exit 2
fi

labels=(
  'type:story|1D76DB|User story'
  'type:task|C5DEF5|Engineering task'
  'type:bug|D73A4A|Defect'
  'type:spike|FBCA04|Time-boxed investigation'
  'area:frontend|0E8A16|Vue application'
  'area:backend|5319E7|FastAPI application'
  'area:processing|006B75|PDAL and conversion'
  'area:infra|BFD4F2|CI, Docker, tooling'
  'area:docs|0075CA|Documentation'
  'priority:P0|B60205|Required for MVP demo'
  'priority:P1|D93F0B|After P0 is stable'
  'priority:P2|EDEDED|Outside MVP'
)
milestones=('Sprint 1' 'Sprint 2' 'Sprint 3' 'Sprint 4' 'v1.0-demo')

printf '%s\n' 'Planned remote changes:'
for item in "${labels[@]}"; do
  printf '%s\n' "- create or update label ${item%%|*}"
done
for milestone in "${milestones[@]}"; do
  printf '%s\n' "- create milestone $milestone if absent"
done

if [ "$apply" = false ]; then
  printf '%s\n' 'Dry run only. Re-run with --apply after explicit team approval.'
  exit 0
fi

command -v gh >/dev/null 2>&1 || { printf '%s\n' 'gh CLI is required.' >&2; exit 1; }
gh auth status >/dev/null

for item in "${labels[@]}"; do
  IFS='|' read -r name color description <<< "$item"
  gh label create "$name" --color "$color" --description "$description" --force
done

for title in "${milestones[@]}"; do
  existing=$(gh api --paginate 'repos/{owner}/{repo}/milestones?state=all&per_page=100' --jq ".[] | select(.title == \"$title\") | .number" | head -n 1)
  if [ -z "$existing" ]; then
    gh api --method POST 'repos/{owner}/{repo}/milestones' -f "title=$title" >/dev/null
  fi
done

printf '%s\n' 'Labels and milestones are configured.'
