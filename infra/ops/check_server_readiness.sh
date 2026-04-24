#!/usr/bin/env bash
set -euo pipefail

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-18080}"
COMPOSE_PROJECT_DIR="${COMPOSE_PROJECT_DIR:-$(pwd)}"

echo "== biomed-news-app server readiness =="
echo "project_dir=${COMPOSE_PROJECT_DIR}"
echo "target=http://${APP_HOST}:${APP_PORT}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing command: $1" >&2
    exit 1
  }
}

require_cmd docker
require_cmd curl

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon unavailable" >&2
  exit 1
fi

echo "-- docker compose config"
docker compose -f "${COMPOSE_PROJECT_DIR}/docker-compose.yml" --env-file "${COMPOSE_PROJECT_DIR}/.env" config >/dev/null

echo "-- docker compose ps"
docker compose -f "${COMPOSE_PROJECT_DIR}/docker-compose.yml" --env-file "${COMPOSE_PROJECT_DIR}/.env" ps

echo "-- nginx root"
curl -fsS -o /dev/null -D - "http://${APP_HOST}:${APP_PORT}/" | sed -n '1,5p'

echo "-- api health"
curl -fsS "http://${APP_HOST}:${APP_PORT}/api/health"
echo

echo "-- api news sample"
curl -fsS "http://${APP_HOST}:${APP_PORT}/api/news?page=1&page_size=3" | head -c 800
echo
echo

echo "-- api today-summary"
curl -fsS "http://${APP_HOST}:${APP_PORT}/api/news/today-summary" | head -c 800
echo
echo

echo "-- nginx health"
curl -fsS "http://${APP_HOST}:${APP_PORT}/nginx-health"
echo

echo "server readiness check completed"
