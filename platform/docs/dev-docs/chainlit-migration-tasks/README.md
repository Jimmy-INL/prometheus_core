# Tasks — Standalone FastAPI Backend

Ordered, executable steps for building a standalone **FastAPI backend** (`backend/`)
that replaces Chainlit's server role while defining its own JSON/SSE contract.

> **Status (branch `old-frontend-removal`):** the backend build (steps 00–10) is **done**, and
> the destructive follow-up has since landed — `chat-backend/` was renamed to `backend/`,
> `frontend-react/` was renamed to `frontend/`, and the **old Chainlit `frontend/` app plus the
> `chainlit-frontend` service were removed**. So `frontend/` is now the in-house React app, and
> the "additive / keep Chainlit untouched" ground rules below describe the *build phase*, not the
> current tree. The remaining code-level Chainlit/recoil cleanup lives in the React cutover
> ([`frontend/README.md`](frontend/README.md), Step 09).

Full design lives in the approved plan: `~/.claude/plans/re-explore-the-current-state-logical-harp.md`.

## Ground rules (build phase — historical)

- **Additive, not destructive.** New `backend/` service on a new port; during the build the
  Chainlit `frontend/` app and `chainlit-frontend` service were left in place. *(Both have since
  been removed on this branch — see the Status note above.)*
- **Port, don't couple.** Reusable modules were copied out of the Chainlit app's `frontend/utils/`
  and adapted; the originals were later deleted with the Chainlit app (recover from git history).
- **Own the contract.** Our wire models (`app/contract.py`) mirror `prometheus_api`'s
  `ConversationResponse` but are defined independently. Normalize at the service boundary;
  never leak base-image types onto the wire.
- Python 3.13, `uv`-managed, matching the client-agent/infra convention.

## Step order

| # | File | Summary | Depends on | Status |
|---|------|---------|------------|--------|
| 00 | `00-scaffold-tasks-and-service-skeleton.md` | Create `backend/` skeleton, pyproject, app + `/healthz`, config | — | ✅ Done |
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

> **Pre-PR review:** a full point-in-time verification of this branch (offline gates + live `make up` smoke + a 7-dimension adversarial bug-hunt) is recorded in [`pre-pr-review.md`](pre-pr-review.md) — read it before merge.

## Reusable sources (ported from the now-removed Chainlit `frontend/`; see git history)

These paths lived in the **old Chainlit `frontend/` app that this branch deleted**; each was
ported into `backend/app/` during the build (arrows point at the resulting live module):

- `utils/a2a_client.py` → `backend/app/a2a_client.py` — `A2AClient` (pure httpx + A2A JSON-RPC), `stage_upload`, contract re-export
- `utils/task_events.py` → `backend/app/task_events.py` — Redis pub/sub for background tasks
- `utils/uri_resolver.py` → `backend/app/uri_resolver.py` — `resolve_to_local_path` (file/http/deeplynx)
- `utils/conversation_state_client.py` → `backend/app/conversation_state.py` — read-only Redis history
- `utils/settings.py` + `config.yml` → `backend/app/config.py` + `backend/app/config.yml` — settings pattern
- `components/message_handler.py` → `backend/app/services/chat.py` (+ `services/uploads.py`) — orchestration logic, ported non-blocking
- `main.py` → `backend/app/security.py` + `routers/{auth,config,sessions,conversations}.py` — auth callbacks, chat profiles, `/history`, session init
