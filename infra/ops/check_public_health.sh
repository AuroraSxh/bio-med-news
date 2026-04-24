#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-}"
if [[ -z "${BASE_URL}" ]]; then
  echo "usage: $0 http://118.178.195.6:18080" >&2
  exit 1
fi

health_body="$(curl -fsS "${BASE_URL%/}/api/health")"
echo "${health_body}"

case "${health_body}" in
  *'"status":"ok"'*|*'"status": "ok"'*)
    ;;
  *)
    echo "health check did not return status=ok" >&2
    exit 1
    ;;
esac

case "${health_body}" in
  *'"database":"ok"'*|*'"database": "ok"'*)
    ;;
  *)
    echo "health check did not return database=ok" >&2
    exit 1
    ;;
esac

echo "public health check passed for ${BASE_URL%/}/api/health"
