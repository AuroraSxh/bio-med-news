# DEPLOYMENT.md

# Deployment Guide

## 1. Deployment target

This application is deployed as a Docker Compose stack behind Nginx.

Public access pattern:

- `http://118.178.195.6:18080/`

Nginx is the only public-facing service.  
All other services stay on the internal Docker network.
The default Compose deployment exposes exactly one public host port from Nginx.
The default Nginx config is HTTP-only and does not require certificate files.

---

## 2. Stack summary

Services in the deployment stack:

- `nginx`
- `frontend`
- `backend`
- `worker`
- `postgres`

Routing model:

- `/` -> frontend
- `/api/` -> backend

The worker runs scheduled ingestion and daily summary generation independently of the web request path.

Public exposure rule:

- only the Nginx service may publish a host port
- the default stack publishes one host port only: `APP_PORT`
- `backend`, `frontend`, `worker`, and `postgres` stay internal to the Docker network

---

## 3. Required files

At minimum, deployment expects these files to exist and be configured:

- `docker-compose.yml`
- `.env`
- `infra/nginx/default.conf`
- `frontend/Dockerfile`
- `backend/Dockerfile`

Documentation files that should stay aligned:

- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/API_SPEC.md`
- `docs/DEPLOYMENT.md`

---

## 4. Environment variables

The runtime depends on `.env`.

Recommended minimum variables:

### Public port
- `APP_PORT`

### Frontend
- `NEXT_PUBLIC_APP_NAME`
- `NEXT_PUBLIC_API_BASE_PATH`

### Database
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`

### Backend / worker
- `GLM5_BASE_URL`
- `GLM5_API_KEY`
- `GLM5_MODEL_NAME`
- `INGESTION_TIMEZONE`
- `INGESTION_SCHEDULE_HOURS`
- `INGESTION_MAX_ITEMS_PER_SOURCE`
- `INGESTION_SOURCES_JSON`
- `WORKER_RUN_ON_STARTUP`
- `SOURCE_CONFIG_PATH`
- `SOURCE_REQUEST_TIMEOUT_SECONDS`
- `SOURCE_REQUEST_MAX_ATTEMPTS`
- `SOURCE_REQUEST_BACKOFF_SECONDS`
- `GLM5_REQUEST_TIMEOUT_SECONDS`
- `GLM5_REQUEST_MAX_ATTEMPTS`
- `GLM5_REQUEST_BACKOFF_SECONDS`
- `SEED_SAMPLE_DATA`
- `LOG_LEVEL`
- `LOG_FORMAT`
- `APP_ENV`
- `ADMIN_REFRESH_TOKEN`

---

## 5. Example `.env`

A practical example:

~~~env
APP_PORT=18080

NEXT_PUBLIC_APP_NAME=Biomed / Cell Therapy Daily
NEXT_PUBLIC_API_BASE_PATH=/api

POSTGRES_DB=biomed_news
POSTGRES_USER=biomed
POSTGRES_PASSWORD=replace_with_a_strong_password

DATABASE_URL=postgresql://biomed:replace_with_a_strong_password@postgres:5432/biomed_news

GLM5_BASE_URL=http://host.docker.internal:8001
GLM5_API_KEY=replace_with_the_real_glm5_key
GLM5_MODEL_NAME=glm5

INGESTION_TIMEZONE=Asia/Shanghai
INGESTION_SCHEDULE_HOURS=8,12,18
INGESTION_MAX_ITEMS_PER_SOURCE=12
INGESTION_SOURCES_JSON=
WORKER_RUN_ON_STARTUP=true
SOURCE_CONFIG_PATH=config/sources.json
SOURCE_REQUEST_TIMEOUT_SECONDS=15
SOURCE_REQUEST_MAX_ATTEMPTS=3
SOURCE_REQUEST_BACKOFF_SECONDS=1.5
GLM5_REQUEST_TIMEOUT_SECONDS=300
GLM5_REQUEST_MAX_ATTEMPTS=3
GLM5_REQUEST_BACKOFF_SECONDS=2
SEED_SAMPLE_DATA=false
LOG_LEVEL=INFO
LOG_FORMAT=text
APP_ENV=production
ADMIN_REFRESH_TOKEN=replace_with_a_long_random_token
~~~

`INGESTION_SOURCES_JSON` is optional. When present, it overrides `SOURCE_CONFIG_PATH` and should be a JSON array of source objects:

~~~json
[
  {
    "name": "Fierce Biotech",
    "feed_url": "https://www.fiercebiotech.com/rss/xml",
    "max_items": 12
  }
]
~~~

---

## 6. Important note about GLM5 connectivity

There are two common deployment situations.

### Case A: GLM5 is reachable by hostname or IP from inside Docker containers

This is the simplest case.

Set:
- `GLM5_BASE_URL` to the actual reachable URL
- `GLM5_API_KEY` to the real key

Example shape:
- `http://10.x.x.x:PORT/...`
- `http://172.x.x.x:PORT/...`
- `http://your-internal-hostname:PORT/...`

### Case B: GLM5 is running on the Docker host itself

In this case, do not assume `host.docker.internal` will always work on Linux servers unless explicitly configured.

Safer choices:

1. Use the host machine's reachable LAN/private IP.
2. Add host-gateway mapping in Compose if you intentionally want to use `host.docker.internal`.

If you choose the second option, add this under both `backend` and `worker` in `docker-compose.yml`:

~~~yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
~~~

---

## 7. First-time setup

### 7.1 Create `.env`

If you do not already have one:

~~~bash
cp .env.example .env
~~~

Then edit `.env` with real values.

### 7.2 Validate Compose config

~~~bash
docker compose config
~~~

This catches many syntax or interpolation problems before startup.

### 7.3 Build and start

~~~bash
docker compose up -d --build
~~~

---

## 8. Common operational commands

### Start services

~~~bash
docker compose up -d
~~~

### Build and start again

~~~bash
docker compose up -d --build
~~~

### Stop services

~~~bash
docker compose down
~~~

### Stop services and remove database volume

Use this only if you intentionally want to remove persisted PostgreSQL data.

~~~bash
docker compose down -v
~~~

### View running containers

~~~bash
docker compose ps
~~~

### View logs for all services

~~~bash
docker compose logs -f
~~~

### View logs for backend only

~~~bash
docker compose logs -f backend
~~~

### View logs for worker only

~~~bash
docker compose logs -f worker
~~~

### View logs for nginx only

~~~bash
docker compose logs -f nginx
~~~

---

## 9. Health and verification

After startup, verify these things.

### 9.1 Nginx is up

Check container status:

~~~bash
docker compose ps
~~~

### 9.2 Backend health endpoint works

~~~bash
curl http://127.0.0.1:${APP_PORT:-18080}/api/health
~~~

Expected:
- HTTP 200
- lightweight health response with `database: "ok"` when PostgreSQL is reachable
- for public checks, the same route should work via Nginx: `http://118.178.195.6:${APP_PORT:-18080}/api/health`

### 9.3 Database-backed data exists

Phase 4 initializes the minimal schema at backend startup. The worker performs RSS-based ingestion and stores processed data in PostgreSQL. Deterministic sample seeding is disabled by default and only runs when `SEED_SAMPLE_DATA=true`.

If the configured feeds do not publish at least three same-day UTC items, the stored daily summary may use the latest processed database items as a controlled MVP fallback. This keeps the homepage useful while preserving source traceability.

Verify through Nginx:

~~~bash
curl http://127.0.0.1:${APP_PORT:-18080}/api/news
curl http://127.0.0.1:${APP_PORT:-18080}/api/news/today-summary
~~~

Manual one-shot worker run inside Compose:

~~~bash
docker compose run --rm worker python -m worker.run_worker --once
~~~

### 9.4 Homepage loads

Open:

- `http://118.178.195.6:18080/`

If `APP_PORT=80`, the expected production URL is:

- `http://118.178.195.6/`

Or locally on the server:

~~~bash
curl -I http://127.0.0.1:${APP_PORT:-18080}/
~~~

### 9.5 Worker is running

Check worker logs:

~~~bash
docker compose logs -f worker
~~~

Look for:
- scheduler startup
- source fetch start/end logs
- normalization and dedupe counts
- classification/enrichment logs
- summary generation outcome

If `LOG_FORMAT=json`, the worker and backend emit machine-readable fields such as `attempt`, `status_code`, `retryable`, `source_name`, and `schema_name`.

### 9.6 Manual refresh

Manual refresh runs the ingestion cycle in the backend process and requires `ADMIN_REFRESH_TOKEN`.

~~~bash
curl -X POST \
  -H "X-Admin-Token: ${ADMIN_REFRESH_TOKEN}" \
  http://127.0.0.1:${APP_PORT:-18080}/api/admin/refresh
~~~

If another manual refresh is already running in the same backend process, the endpoint returns `409 Conflict`. This is a lightweight MVP safeguard, not a distributed cross-container lock.

### 9.7 External monitoring plan

Recommended target:

- `GET http://118.178.195.6:${APP_PORT:-18080}/api/health`

Recommended monitor settings:

- interval: 5 minutes
- timeout: 30 seconds
- alert after 2 consecutive failures
- accepted status: HTTP 200 only
- optional response assertion: body contains `"status":"ok"` and `"database":"ok"`

Practical provider options:

1. UptimeRobot:
   - monitor type: HTTP(s)
   - URL: public `/api/health`
   - keyword mode: require `status":"ok`
2. Healthchecks.io or cron-based shell check:
   - run [`infra/ops/check_public_health.sh`](/Users/aurorasxh/codex_test/biomed-news-app/infra/ops/check_public_health.sh) from a trusted host
   - alert on non-zero exit code

Do not point the uptime monitor at `/`, because the homepage depends on frontend rendering and is a noisier signal than the dedicated health route.

---

## 10. Updating the app

When code changes:

~~~bash
docker compose up -d --build
~~~

If only environment variables changed, a rebuild may not always be required, but restart is still needed.

---

## 11. Port changes

To move the app to a different public port, edit:

- `APP_PORT` in `.env`

Then restart:

~~~bash
docker compose up -d
~~~

No Nginx internal config change is needed for a simple host-port remap, because the container still listens on port 80 internally.

---

## 11A. Server deployment checklist

Use this checklist on the target Linux host such as `118.178.195.6`.

### Before deployment

- confirm SSH access to `118.178.195.6`
- confirm the host clock is sane: `date` and `timedatectl status`
- confirm Docker Engine is installed: `docker --version`
- confirm Compose plugin is installed: `docker compose version`
- confirm Docker daemon is running: `docker info`
- confirm security group allows the chosen public app port, such as `18080/tcp`
- confirm PostgreSQL port is not publicly exposed in the cloud security group
- confirm only Nginx public ports are mapped in `docker-compose.yml`
- confirm `.env` contains a real `POSTGRES_PASSWORD`, `ADMIN_REFRESH_TOKEN`, and GLM5 settings
- confirm `docker compose config` succeeds
- confirm `infra/nginx/ssl/` contents match the intended HTTP-only or HTTPS deployment mode

### Deploy / update

- `docker compose up -d --build`
- `docker compose ps`
- `docker compose logs --tail=100 backend`
- `docker compose logs --tail=100 worker`
- `docker compose logs --tail=100 nginx`

### Public smoke checks

- `curl -I http://127.0.0.1:${APP_PORT:-18080}/`
- `curl http://127.0.0.1:${APP_PORT:-18080}/api/health`
- `curl http://127.0.0.1:${APP_PORT:-18080}/api/news?page=1&page_size=3`
- `curl http://127.0.0.1:${APP_PORT:-18080}/api/news/today-summary`
- if admin refresh is enabled, run one authenticated `POST /api/admin/refresh`

### Post-deploy operations

- install an external uptime monitor against `/api/health`
- keep at least one recent database backup or volume snapshot before risky upgrades
- verify worker logs show scheduler startup and at least one successful ingestion pass
- verify GLM5 failures, if any, are visible in logs with retry metadata
- record the exact deployed `.env` and image build time for rollback reference

### Backup / restore drill

Take a logical PostgreSQL backup:

~~~bash
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > "backup-$(date +%F-%H%M%S).sql"
~~~

Minimum restore rehearsal:

1. create a temporary database inside the same PostgreSQL container
2. restore the dump into that temporary database
3. verify the restore completed without SQL errors
4. query `/api/news` and `/api/news/today-summary` against the real app before deleting the temporary database

Example temporary restore sequence:

~~~bash
docker compose exec postgres psql -U "${POSTGRES_USER}" -c 'CREATE DATABASE biomed_news_restore_check;'
cat backup-YYYY-MM-DD-HHMMSS.sql | docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d biomed_news_restore_check
docker compose exec postgres psql -U "${POSTGRES_USER}" -d biomed_news_restore_check -c 'SELECT COUNT(*) FROM news_items;'
docker compose exec postgres psql -U "${POSTGRES_USER}" -c 'DROP DATABASE biomed_news_restore_check;'
~~~

### Manual refresh acceptance

When `ADMIN_REFRESH_TOKEN` is configured, validate one manual refresh end to end:

~~~bash
curl -i -X POST \
  -H "X-Admin-Token: ${ADMIN_REFRESH_TOKEN}" \
  http://127.0.0.1:${APP_PORT:-18080}/api/admin/refresh
~~~

Confirm:

- HTTP `202 Accepted`
- backend logs show one `admin_refresh` ingestion run
- worker/backfill logic does not crash on source or GLM5 failures
- `/api/news/today-summary` still returns a valid payload after the refresh
- a second overlapping request returns `409 Conflict` if intentionally triggered concurrently

### Local helper

For repeatable host checks, run:

~~~bash
bash infra/ops/check_server_readiness.sh
~~~

---

## 12. Troubleshooting

### 12.1 Frontend loads but API fails

Likely causes:
- backend container unhealthy
- `/api/health` route missing or failing
- backend failed DB connection
- nginx backend routing mismatch

Check:

~~~bash
docker compose logs -f backend
docker compose logs -f nginx
~~~

### 12.2 Backend cannot connect to PostgreSQL

Check:
- `DATABASE_URL`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- whether `postgres` is healthy in `docker compose ps`

### 12.3 Worker cannot reach GLM5

Check:
- `GLM5_BASE_URL`
- `GLM5_API_KEY`
- `GLM5_REQUEST_MAX_ATTEMPTS`
- `GLM5_REQUEST_BACKOFF_SECONDS`
- firewall / VPN / routing
- whether the URL is reachable from inside the container

You can test from the backend or worker container shell if needed.

### 12.4 `host.docker.internal` does not work

This is common on Linux without explicit support.

Preferred fix:
- use an actual reachable host IP

Alternative:
- add `extra_hosts`
- redeploy containers

### 12.5 Nginx starts but homepage is blank or 502

Check:
- frontend build succeeded
- backend health succeeded
- nginx routes point to correct service names
- service names in `default.conf` match Compose service names exactly
- `nginx` is healthy in `docker compose ps`

### 12.6 External uptime monitor reports failures

Check:

- whether `/api/health` returns `503` because PostgreSQL is unavailable
- whether the public port is open in the cloud security group
- whether Nginx is the only public service bound on the host
- whether the monitor is asserting too much beyond `status=ok` and `database=ok`
- whether the public IP or port changed after redeploy

### 12.7 TLS enablement is incomplete

Default MVP deployment is HTTP on one public port. If you explicitly enable HTTPS later, add a dedicated SSL server block first, then verify:

- certificate files exist at `infra/nginx/ssl/fullchain.pem` and `infra/nginx/ssl/privkey.pem`
- private key permissions are restricted
- Nginx config validates before reload

Recommended validation:

~~~bash
docker compose exec nginx nginx -t
~~~

---

## 13. Operational principles

- only Nginx should expose a public port
- do not hardcode secrets in source code
- keep `.env.example` aligned with required runtime variables
- keep docs updated whenever routes, service names, ports, or env vars change
- keep worker independent from the request/response path

---

## 14. Recommended next improvements

After the Phase 4 MVP deployment works, good next steps are:

- add DB migration support before larger schema changes
- monitor current source reliability for several days before expanding the source list
- add source-level health and last-run metadata
- add tests around source parsing, scheduler fallback behavior, and GLM5 malformed-output fallbacks
- add source-level configuration management
- add optional HTTPS termination if public internet exposure grows
