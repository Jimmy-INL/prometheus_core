import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from state.base import StateRepository
from models.state import SessionRecord, MessageRecord, WorkflowStepRecord

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    response_type TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    workflow_id TEXT,
    step_name TEXT NOT NULL,
    step_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    input_data TEXT,
    output_data TEXT,
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_session_id ON workflow_steps(session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow_id ON workflow_steps(workflow_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStateRepository(StateRepository):
    def __init__(self, db_path: str = "data/prometheus.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # -- Sessions --

    async def create_session(self, user_id: str) -> SessionRecord:
        session_id = str(uuid.uuid4())
        now = _now()
        await self._db.execute(
            "INSERT INTO sessions (id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, now, now),
        )
        await self._db.commit()
        return SessionRecord(id=session_id, user_id=user_id, created_at=now, updated_at=now)

    async def get_session(self, session_id: str) -> Optional[SessionRecord]:
        cursor = await self._db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return SessionRecord(**dict(row))

    async def list_sessions(self, user_id: str) -> list[SessionRecord]:
        cursor = await self._db.execute(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [SessionRecord(**dict(r)) for r in rows]

    # -- Messages --

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        response_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> MessageRecord:
        msg_id = str(uuid.uuid4())
        now = _now()
        meta_json = json.dumps(metadata) if metadata else None
        await self._db.execute(
            "INSERT INTO messages (id, session_id, role, content, response_type, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, response_type, meta_json, now),
        )
        await self._db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        await self._db.commit()
        return MessageRecord(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            response_type=response_type,
            metadata=metadata,
            created_at=now,
        )

    async def get_messages(self, session_id: str) -> list[MessageRecord]:
        cursor = await self._db.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else None
            results.append(MessageRecord(**d))
        return results

    # -- Workflow Steps --

    async def add_workflow_step(
        self,
        session_id: str,
        workflow_id: str,
        step_name: str,
        step_type: str,
        input_data: Optional[dict] = None,
    ) -> WorkflowStepRecord:
        step_id = str(uuid.uuid4())
        now = _now()
        input_json = json.dumps(input_data) if input_data else None
        await self._db.execute(
            "INSERT INTO workflow_steps "
            "(id, session_id, workflow_id, step_name, step_type, status, input_data, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (step_id, session_id, workflow_id, step_name, step_type, input_json, now),
        )
        await self._db.commit()
        return WorkflowStepRecord(
            id=step_id,
            session_id=session_id,
            workflow_id=workflow_id,
            step_name=step_name,
            step_type=step_type,
            status="pending",
            input_data=input_data,
            created_at=now,
        )

    async def update_workflow_step(
        self,
        step_id: str,
        status: str,
        output_data: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> Optional[WorkflowStepRecord]:
        now = _now()
        output_json = json.dumps(output_data) if output_data else None

        completed_at = now if status in ("completed", "failed") else None
        started_at = now if status == "running" else None

        # Build the update dynamically to avoid overwriting started_at if already set
        await self._db.execute(
            "UPDATE workflow_steps SET status = ?, output_data = ?, error_message = ?, "
            "completed_at = COALESCE(?, completed_at), "
            "started_at = COALESCE(started_at, ?) "
            "WHERE id = ?",
            (status, output_json, error_message, completed_at, started_at, step_id),
        )
        await self._db.commit()

        cursor = await self._db.execute(
            "SELECT * FROM workflow_steps WHERE id = ?", (step_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["input_data"] = json.loads(d["input_data"]) if d["input_data"] else None
        d["output_data"] = json.loads(d["output_data"]) if d["output_data"] else None
        return WorkflowStepRecord(**d)

    async def get_workflow_steps(self, session_id: str) -> list[WorkflowStepRecord]:
        cursor = await self._db.execute(
            "SELECT * FROM workflow_steps WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["input_data"] = json.loads(d["input_data"]) if d["input_data"] else None
            d["output_data"] = json.loads(d["output_data"]) if d["output_data"] else None
            results.append(WorkflowStepRecord(**d))
        return results
