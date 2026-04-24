---
name: deploy-ops
description: Use this skill when changing Docker Compose, container wiring, Nginx reverse proxy behavior, environment variables, health checks, or deployment documentation for this project. Do not use it for product copy, UI styling, or news-classification logic.
---

# Deploy Ops Skill

## Purpose

Maintain a stable deployment path for the application on the target server.

This repository uses:
- Docker Compose for orchestration
- Nginx as the single public entrypoint
- internal container networking for frontend/backend/database communication

## Fixed deployment model

Keep this shape unless explicitly asked to change it:
- nginx service exposed publicly on one port
- frontend service internal to compose network
- backend service internal to compose network
- worker service internal to compose network
- postgres service internal to compose network

Do not default to manual multi-terminal startup as the main operational path.

## Reverse proxy expectations

Nginx should:
- serve as the only public entrypoint
- route `/` to the frontend
- route `/api/` to the backend
- forward the relevant headers
- keep configuration readable and minimal

## Environment variable discipline

- use `.env` / compose env wiring
- never hardcode secrets
- document any newly required env vars in docs/DEPLOYMENT.md and `.env.example`
- keep frontend and backend env boundaries clear

## Health and operability

Where practical, include:
- health checks
- restart policies
- readable container names or service names
- clear logs for startup failures

Prefer boring, inspectable operations over clever container tricks.

## Change management

When changing deployment behavior:
1. update compose config
2. update nginx config when routing changes
3. update docs/DEPLOYMENT.md
4. verify service dependencies and startup assumptions
5. avoid breaking the single-public-port model

## Validation expectations

After infra changes, verify at least:
- compose file is valid
- routing assumptions still make sense
- service names referenced by nginx match compose services
- environment variable names are documented consistently
