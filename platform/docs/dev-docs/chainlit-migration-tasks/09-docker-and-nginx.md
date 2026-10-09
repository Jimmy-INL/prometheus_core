# 09 — Docker, compose, nginx; fix pre-existing prod breakage

> **Status: ✅ Done.** The `backend` service, `backend/Dockerfile`, and nginx examples all
> landed. Reality has since moved past parts of this doc: the Chainlit `frontend` app and the
> `chainlit-frontend` service were **removed**, and nginx already proxies `→ backend:8000` in
> both `frontend/nginx.conf` (prod build) and `backend/nginx.example.conf` (reference) — there
> is **no `nginx1.conf`** — so the nginx / `depends_on: chainlit-frontend` fix-ups below are
> moot. The only Chainlit residue left in compose is a `VITE_CHAINLIT_SERVER` env value + a
> commented `chainlit-frontend` `depends_on`, cleaned up in the React cutover
> ([`frontend/README.md`](frontend/README.md), Step 09).

## Goal

Package `backend/` as a container, wire it into the compose stack as a **new additive
service**, and provide an nginx example that proxies `/api/` with SSE tuning.
Also fix two pre-existing breakages found during exploration.

## Files to create / modify

- **Create** `backend/Dockerfile`
- **Create** `backend/docker-compose.yml` (per-service fragment) OR add a service block
  to root `docker-compose.yml` — match the repo convention (root compose defines services
  directly; `agents/*/docker-compose.yml` are the per-service fragments auto-included via
  `make generate`). Since backend is not under `agents/`, add it to the **root
  `docker-compose.yml`** as a new service.
- **Create** an nginx example (e.g. `backend/nginx.example.conf`) documenting the `/api/`
  proxy for whoever wires the React SPA later.
- ~~**Modify** `frontend/Dockerfile` nginx path (the `nginx1.conf` breakage)~~ — **done**: the
  prod stage uses `frontend/nginx.conf`, which proxies `/api/` → `backend:8000`; there is no
  `nginx1.conf`.
- ~~**Modify** root `docker-compose.yml` — remove `frontend-prod: depends_on: chainlit-frontend`~~
  — **done**: the `chainlit-frontend` service is removed (only a commented `depends_on` remains).

## Details

### `backend/Dockerfile`
- Python 3.13 base. Install `uv`, `uv sync`. If `prometheus_api` is pulled from the private
  git/registry, replicate the auth/CA approach used by the client-agent Dockerfile and the
  `frontend` cert stage (`COPY --from=certs ca-bundle.pem ...`). Expose the container
  port (8000 to match the platform convention), run `uvicorn app.main:app --host 0.0.0.0`.

### Root `docker-compose.yml` service block
- Name `backend`, `container_name: backend`, build `./backend`, host port e.g.
  `${BACKEND_PORT:-8600}:8000`. Use the `*common-env` anchor (agent secret, redis, etc.)
  and add `CLIENT_AGENT_URL=http://client-agent:8000`, `REDIS_URL`, `AGENT_SECRET`,
  `BACKEND_JWT_SECRET`. Attach to `agent-network`. `depends_on`: redis (healthy),
  client-agent. Mount `*common-volumes` if the artifact cache under `/app/shared` is used.
- **Do not** touch or uncomment the `chainlit-frontend` service. *(It has since been removed
  entirely on this branch; only a commented `depends_on` + a `VITE_CHAINLIT_SERVER` env value
  linger, dropped in the React cutover Step 09.)*

### nginx example (`/api/` + SSE)
```
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
location /api/events {
    proxy_pass http://backend:8000;
    proxy_buffering off;                 # SSE
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
}
```

### `.env.example`
- Add `BACKEND_PORT=8600` and `BACKEND_JWT_SECRET=` (with the same
  `python3 -c "import secrets; ..."` generation hint already added there).

## Acceptance check

- `docker compose build backend` succeeds.
- `docker compose up backend` (with redis + client-agent up) → `/healthz` reachable on
  the host port.
- `frontend` prod target builds again (Dockerfile nginx path fixed).
- `PROFILE=prod` no longer references the removed chainlit-frontend.
- `make up` / `make generate` still work (backend in root compose doesn't disturb the
  `agents/*` generation).
