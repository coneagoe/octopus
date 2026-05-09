#!/bin/sh
set -eu

prompt="${1:-}"

case "$prompt" in
  *Username* | *username*)
    printf '%s\n' "x-access-token"
    ;;
  *Password* | *password*)
    if [ -z "${GITHUB_PAT:-}" ]; then
      echo "GITHUB_PAT is not set" >&2
      exit 1
    fi
    printf '%s\n' "$GITHUB_PAT"
    ;;
  *)
    echo "Unsupported Git credential prompt: $prompt" >&2
    exit 1
    ;;
esac
