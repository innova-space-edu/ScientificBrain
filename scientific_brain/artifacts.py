from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .memory import ScientificMemory


ARTIFACT_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_artifacts (
  artifact_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  producer_agent TEXT NOT NULL,
  stage TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  revision INTEGER NOT NULL DEFAULT 1,
  accepted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(session_id, artifact_type, revision)
);
CREATE INDEX IF NOT EXISTS idx_research_artifacts_session
  ON research_artifacts(session_id, stage, artifact_type);
"""


class ArtifactRecord(BaseModel):
    artifact_id: str
    session_id: str
    artifact_type: str
    producer_agent: str
    stage: str
    payload: Any
    evidence_ids: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)
    accepted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LocalArtifactStore:
    def __init__(self, memory: ScientificMemory) -> None:
        self.memory = memory
        self.memory.conn.executescript(ARTIFACT_SCHEMA)

    def save(self, artifact: ArtifactRecord) -> None:
        self.memory.conn.execute(
            """INSERT OR REPLACE INTO research_artifacts(
                 artifact_id,session_id,artifact_type,producer_agent,stage,payload_json,
                 evidence_ids_json,revision,accepted,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                artifact.artifact_id,
                artifact.session_id,
                artifact.artifact_type,
                artifact.producer_agent,
                artifact.stage,
                json.dumps(artifact.payload, ensure_ascii=False, default=str),
                json.dumps(artifact.evidence_ids, ensure_ascii=False),
                artifact.revision,
                int(artifact.accepted),
                artifact.created_at.isoformat(),
            ),
        )
        self.memory.conn.commit()

    def _from_row(self, row) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            session_id=row["session_id"],
            artifact_type=row["artifact_type"],
            producer_agent=row["producer_agent"],
            stage=row["stage"],
            payload=json.loads(row["payload_json"]),
            evidence_ids=json.loads(row["evidence_ids_json"]),
            revision=row["revision"],
            accepted=bool(row["accepted"]),
            created_at=row["created_at"],
        )

    def latest(self, session_id: str, artifact_type: str) -> ArtifactRecord | None:
        row = self.memory.conn.execute(
            """SELECT * FROM research_artifacts
               WHERE session_id=? AND artifact_type=?
               ORDER BY revision DESC LIMIT 1""",
            (session_id, artifact_type),
        ).fetchone()
        return self._from_row(row) if row else None

    def for_stage(self, session_id: str, stage: str) -> list[ArtifactRecord]:
        rows = self.memory.conn.execute(
            """SELECT * FROM research_artifacts
               WHERE session_id=? AND stage=?
               ORDER BY created_at, artifact_type, revision""",
            (session_id, stage),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def context(self, session_id: str) -> dict[str, Any]:
        rows = self.memory.conn.execute(
            """SELECT a.* FROM research_artifacts a
               JOIN (
                 SELECT artifact_type, MAX(revision) AS max_revision
                 FROM research_artifacts WHERE session_id=? GROUP BY artifact_type
               ) latest
               ON a.artifact_type=latest.artifact_type AND a.revision=latest.max_revision
               WHERE a.session_id=?""",
            (session_id, session_id),
        ).fetchall()
        return {row["artifact_type"]: self._from_row(row).payload for row in rows}

    def next_revision(self, session_id: str, artifact_type: str) -> int:
        row = self.memory.conn.execute(
            "SELECT COALESCE(MAX(revision),0)+1 FROM research_artifacts WHERE session_id=? AND artifact_type=?",
            (session_id, artifact_type),
        ).fetchone()
        return int(row[0])
