# Tasks — Standalone FastAPI Chat Backend

Ordered, executable steps for building a standalone **FastAPI chat backend** (`chat-backend/`)
that replaces Chainlit's server role while defining its own JSON/SSE contract. This is a
**backend-only** effort: `frontend-react/` (currently coupled to Chainlit via
`@chainlit/react-client`) is rewired in a **separate follow-up**, and the old Chainlit app
(`frontend/`, `chainlit-frontend` service) is **kept untouched**.

Full design lives in the approved plan: `~/.claude/plans/re-explore-the-current-state-logical-harp.md`.

## Ground rules

- **Additive, not destructive.** New `chat-backend/` service on a new port. Do **not** delete
  `frontend/` or touch the `chainlit-frontend` service.
- **Port, don't couple.** Copy reusable modules out of `frontend/utils/` and adapt; the
  originals stay in place as reference.
- **Own the contract.** Our wire models (`app/contract.py`) mirror `prometheus_api`'s
  `ConversationResponse` but are defined independently. Normalize at the service boundary;
  never leak base-image types onto the wire.
- Python 3.13, `uv`-managed, matching the client-agent/infra convention.

## Step order

| # | File | Summary | Depends on | Status |
|---|------|---------|------------|--------|
| 00 | `00-scaffold-tasks-and-service-skeleton.md` | Create `chat-backend/` skeleton, pyproject, app + `/healthz`, config | — | ✅ Done |
| 01 | `01-contract.md` | Freeze `contract.py` (request/response/SSE/form/artifact shapes) — **critical path** | 00 | ✅ Done |
| 02 | `02-auth-and-sessions.md` | JWT cookie auth, IdP interface, session store, `/api/sessions`, `/api/config` | 00, 01 | ✅ Done |
| 03 | `03-lift-shared-utils.md` | Copy + de-Chainlit `a2a_client`, `task_events`, `uri_resolver`, `conversation_state` | 00 | ✅ Done |
| 04 | `04-chat-turn.md` | Non-blocking turn orchestration, `POST /api/chat/messages` | 01, 03 | ✅ Done |
| 05 | `05-events-sse.md` | Per-session event bus + Redis subscriber, `GET /api/events` | 01, 03, 04 | ✅ Done |
| 06 | `06-uploads.md` | `POST /api/uploads` (size limit, MIME, staging) | 01, 03 | ✅ Done |
| 07 | `07-artifacts-proxy.md` | `render_hint` classification + `GET /api/artifacts/{id}/content` | 01, 03, 04 | ✅ Done |
| 08 | `08-conversations-history.md` | `GET /api/conversations/recent` | 03 | ✅ Done |
| 09 | `09-docker-and-nginx.md` | Dockerfile, compose fragment, nginx example; fix pre-existing prod-build breakage | 00 | ✅ Done |
| 10 | `10-verify.md` | httpx/curl status-matrix harness + pytest contract test | all | ✅ Done |

## Reusable sources (in `frontend/`, port from these)

- `utils/a2a_client.py` — `A2AClient` (pure httpx + A2A JSON-RPC), `stage_upload`, contract re-export
- `utils/task_events.py` — Redis pub/sub for background tasks
- `utils/uri_resolver.py` — `resolve_to_local_path` (file/http/deeplynx)
- `utils/conversation_state_client.py` — read-only Redis history
- `utils/settings.py` + `config.yml` — settings pattern
- `components/message_handler.py` — orchestration + rendering logic to port (non-blocking)
- `main.py` — auth callbacks, chat profiles, `/history`, session init
