# 09 — Docker, compose, nginx; fix pre-existing prod breakage

## Goal

Package `chat-backend/` as a container, wire it into the compose stack as a **new additive
service** (Chainlit stays), and provide an nginx example that proxies `/api/` with SSE tuning.
Also fix two pre-existing breakages found during exploration.

## Files to create / modify

- **Create** `chat-backend/Dockerfile`
- **Create** `chat-backend/docker-compose.yml` (per-service fragment) OR add a service block
  to root `docker-compose.yml` — match the repo convention (root compose defines services
  directly; `agents/*/docker-compose.yml` are the per-service fragments auto-included via
  `make generate`). Since chat-backend is not under `agents/`, add it to the **root
  `docker-compose.yml`** as a new service.
- **Create** an nginx example (e.g. `chat-backend/nginx.example.conf`) documenting the `/api/`
  proxy for whoever wires the React SPA later.
- **Modify** `frontend-react/Dockerfile:37` — `COPY frontend-react/nginx.conf` → `nginx1.conf`
  (or revert the rename). Pre-existing prod-build breakage.
- **Modify** root `docker-compose.yml` — remove the stale
  `frontend-react-prod: depends_on: chainlit-frontend` (chainlit-frontend is commented out).

## Details

### `chat-backend/Dockerfile`
- Python 3.13 base. Install `uv`, `uv sync`. If `prometheus_api` is pulled from the private
  git/registry, replicate the auth/CA approach used by the client-agent Dockerfile and the
  `frontend-react` cert stage (`COPY --from=certs ca-bundle.pem ...`). Expose the container
  port (8000 to match the platform convention), run `uvicorn app.main:app --host 0.0.0.0`.

### Root `docker-compose.yml` service block
- Name `chat-backend`, `container_name: chat-backend`, build `./chat-backend`, host port e.g.
  `${CHAT_BACKEND_PORT:-8600}:8000`. Use the `*common-env` anchor (agent secret, redis, etc.)
  and add `CLIENT_AGENT_URL=http://client-agent:8000`, `REDIS_URL`, `AGENT_SECRET`,
  `CHAT_BACKEND_JWT_SECRET`. Attach to `agent-network`. `depends_on`: redis (healthy),
  client-agent. Mount `*common-volumes` if the artifact cache under `/app/shared` is used.
- **Do not** touch or uncomment the `chainlit-frontend` service.

### nginx example (`/api/` + SSE)
```
location /api/ {
    proxy_pass http://chat-backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
location /api/events {
    proxy_pass http://chat-backend:8000;
    proxy_buffering off;                 # SSE
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
}
```

### `.env.example`
- Add `CHAT_BACKEND_PORT=8600` and `CHAT_BACKEND_JWT_SECRET=` (with the same
  `python3 -c "import secrets; ..."` generation hint already added there).

## Acceptance check

- `docker compose build chat-backend` succeeds.
- `docker compose up chat-backend` (with redis + client-agent up) → `/healthz` reachable on
  the host port.
- `frontend-react` prod target builds again (Dockerfile nginx path fixed).
- `PROFILE=prod` no longer references the removed chainlit-frontend.
- `make up` / `make generate` still work (chat-backend in root compose doesn't disturb the
  `agents/*` generation).
