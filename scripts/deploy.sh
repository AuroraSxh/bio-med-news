#!/usr/bin/env bash
# Fast deploy for biomed-news-app.
#
# Usage:
#   bash scripts/deploy.sh                   # fast path: rsync + restart (Python + compose + nginx conf only)
#   bash scripts/deploy.sh backend           # fast-restart backend+worker
#   bash scripts/deploy.sh frontend          # rebuild+recreate frontend (Next.js needs a build)
#   bash scripts/deploy.sh nginx             # reload nginx in-place, no restart
#   REBUILD=1 bash scripts/deploy.sh backend # force backend image rebuild (for dep changes)
#   REBUILD=1 bash scripts/deploy.sh all     # full rebuild of everything
#
# Fast path explained:
#   Backend + worker use bind-mounted source (see docker-compose.yml volumes).
#   Python code changes → rsync + `docker compose restart backend worker` (~3s).
#   Only set REBUILD=1 when pyproject.toml or the Dockerfile itself changed.

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-root@118.178.195.6}"
REMOTE_PATH="${REMOTE_PATH:-/opt/biomed-news-app}"
REBUILD="${REBUILD:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VALID=(backend frontend nginx worker all)
declare -a TARGETS=()
if [[ $# -eq 0 ]]; then
    TARGETS=(backend frontend nginx)
else
    for arg in "$@"; do
        if [[ "${arg}" == "all" ]]; then TARGETS=(backend frontend nginx); break; fi
        ok=0; for v in "${VALID[@]}"; do [[ "${v}" == "${arg}" ]] && ok=1 && break; done
        [[ "${ok}" == "1" ]] || { echo "ERROR: unknown target '${arg}'"; exit 2; }
        TARGETS+=("${arg}")
    done
fi

timed() { local t0=$(date +%s); "$@"; local t1=$(date +%s); printf "[deploy] %-30s %ss\n" "$1" "$((t1-t0))"; }

# ---------- rsync ----------
rsync_project() {
    local excludes=(
        --exclude='.git/' --exclude='node_modules/' --exclude='.next/'
        --exclude='__pycache__/' --exclude='.venv/' --exclude='.pytest_cache/'
        --exclude='*.pyc' --exclude='.DS_Store' --exclude='.claude/'
        --exclude='attime-master.zip' --exclude='*.log'
    )
    # We only need to ship: backend/, frontend/, infra/, docker-compose.yml, scripts/
    # Skip rsync for nginx-only target.
    rsync -az --delete "${excludes[@]}" \
        "${PROJECT_ROOT}/backend/" "${REMOTE_HOST}:${REMOTE_PATH}/backend/"
    rsync -az --delete "${excludes[@]}" \
        "${PROJECT_ROOT}/infra/" "${REMOTE_HOST}:${REMOTE_PATH}/infra/"
    rsync -az "${PROJECT_ROOT}/docker-compose.yml" "${REMOTE_HOST}:${REMOTE_PATH}/docker-compose.yml"
    rsync -az "${PROJECT_ROOT}/scripts/" "${REMOTE_HOST}:${REMOTE_PATH}/scripts/"
    # Frontend only when targeted (it's heavy)
    for t in "${TARGETS[@]}"; do
        if [[ "${t}" == "frontend" ]]; then
            rsync -az --delete "${excludes[@]}" \
                "${PROJECT_ROOT}/frontend/" "${REMOTE_HOST}:${REMOTE_PATH}/frontend/"
            break
        fi
    done
}

# ---------- remote actions ----------
remote() { ssh -o ServerAliveInterval=15 "${REMOTE_HOST}" "cd ${REMOTE_PATH} && $*"; }

restart_backend_fast() {
    # No build — bind-mounted source is already updated via rsync.
    remote "docker compose restart backend worker"
}
rebuild_backend() {
    remote "docker compose build backend && docker compose up -d --force-recreate backend worker"
}
rebuild_frontend() {
    # Next.js has a compiled bundle → always rebuild on frontend deploy.
    remote "docker compose build frontend && docker compose up -d --force-recreate frontend"
}
reload_nginx() {
    remote "docker compose exec -T nginx nginx -t && docker compose exec -T nginx nginx -s reload"
}

t0=$(date +%s)
echo "[deploy] targets: ${TARGETS[*]}  REBUILD=${REBUILD}"
timed rsync_project

for t in "${TARGETS[@]}"; do
    case "${t}" in
        backend|worker)
            if [[ "${REBUILD}" == "1" ]]; then timed rebuild_backend
            else timed restart_backend_fast
            fi
            ;;
        frontend) timed rebuild_frontend ;;
        nginx)    timed reload_nginx ;;
    esac
done

printf "[deploy] TOTAL                          %ss\n" "$(( $(date +%s) - t0 ))"
