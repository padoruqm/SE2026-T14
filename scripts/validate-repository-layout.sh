#!/usr/bin/env bash
set -euo pipefail

required_paths=(
  .github
  frontend/src/app
  frontend/src/features
  frontend/src/shared
  frontend/src/api/generated
  backend/app/api
  backend/app/services
  backend/app/processing
  backend/app/storage
  backend/app/jobs
  backend/app/core
  backend/tests
  data/sample
  scripts
)

missing=0
for path in "${required_paths[@]}"; do
  if [ ! -d "$path" ]; then
    printf '%s\n' "Missing required directory: $path" >&2
    missing=1
  fi
done

for file in README.md .gitignore .env.example .gitmessage .pre-commit-config.yaml CODEOWNERS Makefile; do
  if [ ! -f "$file" ]; then
    printf '%s\n' "Missing required file: $file" >&2
    missing=1
  fi
done

exit "$missing"
