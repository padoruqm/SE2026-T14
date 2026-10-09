#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' 'Usage: validate-commit-msg.sh <commit-message-file>' >&2
  printf '%s\n' '   or: validate-commit-msg.sh --subject "type(scope): subject"' >&2
  exit 2
}

if [ "${1:-}" = "--subject" ]; then
  [ "$#" = 2 ] || usage
  subject=$2
elif [ "$#" = 1 ] && [ -f "$1" ]; then
  IFS= read -r subject < "$1" || true
else
  usage
fi

pattern='^(feat|fix|docs|refactor|test|chore|build|ci|perf)\((upload|viewer|measure|crop|filter|export|api|jobs|processing|storage|infra|docs|deps)\): .+$'

if ! printf '%s\n' "$subject" | grep -Eq "$pattern"; then
  printf '%s\n' "Invalid commit subject: $subject" >&2
  printf '%s\n' 'Expected: type(scope): imperative subject' >&2
  exit 1
fi

commit_subject=${subject#*: }
if [ "${#commit_subject}" -gt 72 ]; then
  printf '%s\n' 'Commit subject must be 72 characters or fewer.' >&2
  exit 1
fi

case "$commit_subject" in
  *.)
    printf '%s\n' 'Commit subject must not end with a period.' >&2
    exit 1
    ;;
esac

case "$(printf '%s' "$commit_subject" | tr '[:upper:]' '[:lower:]')" in
  update|fix|final|wip|wip\ *)
    printf '%s\n' 'Commit subject is too vague; describe the change.' >&2
    exit 1
    ;;
esac
