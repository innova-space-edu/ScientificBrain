from __future__ import annotations

from .memory import ScientificMemory
from .research_contracts import ResearchProjectDefinition


PROJECT_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_definitions (
  project_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  discipline TEXT NOT NULL,
  definition_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class ProjectDefinitionStore:
    def __init__(self, memory: ScientificMemory) -> None:
        self.memory = memory
        self.memory.conn.executescript(PROJECT_SCHEMA)

    def save(self, project: ResearchProjectDefinition) -> None:
        self.memory.conn.execute(
            """INSERT INTO project_definitions(project_id,title,discipline,definition_json,updated_at)
               VALUES(?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(project_id) DO UPDATE SET
                 title=excluded.title,
                 discipline=excluded.discipline,
                 definition_json=excluded.definition_json,
                 updated_at=CURRENT_TIMESTAMP""",
            (project.project_id, project.title, project.discipline, project.model_dump_json()),
        )
        self.memory.conn.commit()

    def load(self, project_id: str) -> ResearchProjectDefinition | None:
        row = self.memory.conn.execute(
            "SELECT definition_json FROM project_definitions WHERE project_id=?",
            (project_id,),
        ).fetchone()
        return ResearchProjectDefinition.model_validate_json(row[0]) if row else None

    def list_ids(self) -> list[str]:
        rows = self.memory.conn.execute(
            "SELECT project_id FROM project_definitions ORDER BY updated_at DESC"
        ).fetchall()
        return [row[0] for row in rows]
