from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import (
    Critique,
    GateResult,
    Paper,
    PaperAnalysis,
    PaperKind,
    ResearchState,
    ReviewDepth,
    SpecialistReview,
)


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS papers (
  canonical_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  abstract TEXT NOT NULL DEFAULT '',
  authors_json TEXT NOT NULL DEFAULT '[]',
  publication_date TEXT,
  journal TEXT,
  doi TEXT UNIQUE,
  arxiv_id TEXT UNIQUE,
  openalex_id TEXT UNIQUE,
  url TEXT,
  cited_by_count INTEGER NOT NULL DEFAULT 0,
  kind TEXT NOT NULL DEFAULT 'unknown',
  topics_json TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL,
  discovered_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS paper_fts USING fts5(
  canonical_id UNINDEXED, title, abstract, topics
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(canonical_id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  section TEXT, page INTEGER, equation TEXT, figure TEXT, strength TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
  claim_id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(canonical_id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  claim_type TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS relations (
  source_claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  relation TEXT NOT NULL CHECK(relation IN ('supports','contradicts','extends','replicates','depends_on')),
  target_claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  rationale TEXT,
  PRIMARY KEY(source_claim_id, relation, target_claim_id)
);
CREATE TABLE IF NOT EXISTS research_sessions (
  session_id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  notes_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS paper_analysis (
  paper_id TEXT PRIMARY KEY REFERENCES papers(canonical_id) ON DELETE CASCADE,
  review_depth TEXT NOT NULL,
  analysis_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS paper_critiques (
  paper_id TEXT PRIMARY KEY REFERENCES papers(canonical_id) ON DELETE CASCADE,
  critique_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS specialist_reviews (
  paper_id TEXT NOT NULL REFERENCES papers(canonical_id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  review_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(paper_id, role)
);
CREATE TABLE IF NOT EXISTS paper_review_status (
  paper_id TEXT PRIMARY KEY REFERENCES papers(canonical_id) ON DELETE CASCADE,
  review_depth TEXT NOT NULL DEFAULT 'metadata_verified',
  source_path TEXT,
  content_sha256 TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS research_states (
  session_id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  state_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS gate_runs (
  gate_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  paper_id TEXT,
  gate_name TEXT NOT NULL,
  passed INTEGER NOT NULL,
  score REAL NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class ScientificMemory:
    def __init__(self, path: str | Path = "scientific_brain.db") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ScientificMemory":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def upsert_paper(self, paper: Paper) -> None:
        payload = (
            paper.canonical_id, paper.title, paper.abstract,
            json.dumps(paper.authors, ensure_ascii=False),
            paper.publication_date.isoformat() if paper.publication_date else None,
            paper.journal, paper.doi, paper.arxiv_id, paper.openalex_id,
            str(paper.url) if paper.url else None, paper.cited_by_count, paper.kind.value,
            json.dumps(paper.plasma_topics, ensure_ascii=False), paper.source,
            paper.discovered_at.isoformat(),
        )
        self.conn.execute(
            """INSERT INTO papers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(canonical_id) DO UPDATE SET
              title=excluded.title, abstract=excluded.abstract, authors_json=excluded.authors_json,
              publication_date=excluded.publication_date, journal=excluded.journal,
              doi=COALESCE(excluded.doi,papers.doi), arxiv_id=COALESCE(excluded.arxiv_id,papers.arxiv_id),
              openalex_id=COALESCE(excluded.openalex_id,papers.openalex_id),
              url=COALESCE(excluded.url,papers.url), cited_by_count=MAX(excluded.cited_by_count,papers.cited_by_count),
              kind=CASE WHEN excluded.kind='unknown' THEN papers.kind ELSE excluded.kind END,
              topics_json=CASE WHEN excluded.topics_json='[]' THEN papers.topics_json ELSE excluded.topics_json END,
              source=excluded.source""",
            payload,
        )
        self.conn.execute("DELETE FROM paper_fts WHERE canonical_id=?", (paper.canonical_id,))
        self.conn.execute(
            "INSERT INTO paper_fts(canonical_id,title,abstract,topics) VALUES(?,?,?,?)",
            (paper.canonical_id, paper.title, paper.abstract, " ".join(paper.plasma_topics)),
        )
        self.conn.execute(
            """INSERT OR IGNORE INTO paper_review_status(paper_id,review_depth)
               VALUES(?,?)""",
            (paper.canonical_id, ReviewDepth.METADATA.value),
        )
        self.conn.commit()

    def _paper_from_row(self, row: sqlite3.Row) -> Paper:
        return Paper(
            canonical_id=row["canonical_id"],
            title=row["title"],
            abstract=row["abstract"],
            authors=json.loads(row["authors_json"]),
            publication_date=row["publication_date"],
            journal=row["journal"],
            doi=row["doi"],
            arxiv_id=row["arxiv_id"],
            openalex_id=row["openalex_id"],
            url=row["url"],
            cited_by_count=row["cited_by_count"],
            kind=PaperKind(row["kind"]),
            plasma_topics=json.loads(row["topics_json"]),
            source=row["source"],
            discovered_at=row["discovered_at"],
        )

    def get_paper(self, paper_id: str) -> Paper | None:
        row = self.conn.execute(
            "SELECT * FROM papers WHERE canonical_id=?", (paper_id,)
        ).fetchone()
        return self._paper_from_row(row) if row else None

    def set_paper_kind(self, paper_id: str, kind: PaperKind) -> None:
        self.conn.execute(
            "UPDATE papers SET kind=? WHERE canonical_id=?",
            (kind.value, paper_id),
        )
        self.conn.commit()

    def list_papers(self, limit: int | None = None) -> list[Paper]:
        sql = "SELECT * FROM papers ORDER BY cited_by_count DESC, publication_date DESC"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return [self._paper_from_row(row) for row in self.conn.execute(sql, params).fetchall()]

    def add_evidence(self, item) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO evidence VALUES(?,?,?,?,?,?,?,?)",
            (item.evidence_id, item.paper_id, item.text, item.section, item.page,
             item.equation, item.figure, item.strength.value),
        )
        self.conn.commit()

    def add_claim(self, claim) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO claims VALUES(?,?,?,?,?,?)",
            (claim.claim_id, claim.paper_id, claim.text, claim.claim_type,
             json.dumps(claim.evidence_ids), claim.confidence),
        )
        self.conn.commit()

    def relate_claims(self, source: str, relation: str, target: str, rationale: str = "") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO relations VALUES(?,?,?,?)",
            (source, relation, target, rationale),
        )
        self.conn.commit()

    def save_analysis(self, analysis: PaperAnalysis) -> None:
        self.conn.execute(
            """INSERT INTO paper_analysis(paper_id,review_depth,analysis_json,updated_at)
               VALUES(?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(paper_id) DO UPDATE SET
                 review_depth=excluded.review_depth,
                 analysis_json=excluded.analysis_json,
                 updated_at=CURRENT_TIMESTAMP""",
            (analysis.paper_id, analysis.review_depth.value, analysis.model_dump_json()),
        )
        for item in analysis.evidence:
            self.add_evidence(item)
        for claim in analysis.claims:
            self.add_claim(claim)
        self.set_review_status(analysis.paper_id, analysis.review_depth)
        self.conn.commit()

    def get_analysis(self, paper_id: str) -> PaperAnalysis | None:
        row = self.conn.execute(
            "SELECT analysis_json FROM paper_analysis WHERE paper_id=?", (paper_id,)
        ).fetchone()
        return PaperAnalysis.model_validate_json(row[0]) if row else None

    def save_critique(self, critique: Critique) -> None:
        self.conn.execute(
            """INSERT INTO paper_critiques(paper_id,critique_json,updated_at)
               VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(paper_id) DO UPDATE SET
                 critique_json=excluded.critique_json, updated_at=CURRENT_TIMESTAMP""",
            (critique.paper_id, critique.model_dump_json()),
        )
        self.conn.commit()

    def get_critique(self, paper_id: str) -> Critique | None:
        row = self.conn.execute(
            "SELECT critique_json FROM paper_critiques WHERE paper_id=?", (paper_id,)
        ).fetchone()
        return Critique.model_validate_json(row[0]) if row else None

    def save_specialist_review(self, review: SpecialistReview) -> None:
        self.conn.execute(
            """INSERT INTO specialist_reviews(paper_id,role,review_json,updated_at)
               VALUES(?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(paper_id,role) DO UPDATE SET
                 review_json=excluded.review_json, updated_at=CURRENT_TIMESTAMP""",
            (review.paper_id, review.role, review.model_dump_json()),
        )
        self.conn.commit()

    def get_specialist_reviews(self, paper_id: str) -> list[SpecialistReview]:
        rows = self.conn.execute(
            "SELECT review_json FROM specialist_reviews WHERE paper_id=? ORDER BY role",
            (paper_id,),
        ).fetchall()
        return [SpecialistReview.model_validate_json(row[0]) for row in rows]

    def set_review_status(
        self,
        paper_id: str,
        depth: ReviewDepth,
        source_path: str | None = None,
        content_sha256: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO paper_review_status(paper_id,review_depth,source_path,content_sha256,updated_at)
               VALUES(?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(paper_id) DO UPDATE SET
                 review_depth=excluded.review_depth,
                 source_path=COALESCE(excluded.source_path,paper_review_status.source_path),
                 content_sha256=COALESCE(excluded.content_sha256,paper_review_status.content_sha256),
                 updated_at=CURRENT_TIMESTAMP""",
            (paper_id, depth.value, source_path, content_sha256),
        )
        self.conn.commit()

    def get_review_status(self, paper_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM paper_review_status WHERE paper_id=?", (paper_id,)
        ).fetchone()
        return dict(row) if row else None

    def save_state(self, state: ResearchState) -> None:
        self.conn.execute(
            """INSERT INTO research_states(session_id,question,state_json,updated_at)
               VALUES(?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(session_id) DO UPDATE SET
                 question=excluded.question,state_json=excluded.state_json,updated_at=CURRENT_TIMESTAMP""",
            (state.session_id, state.question, state.model_dump_json()),
        )
        self.conn.commit()

    def load_state(self, session_id: str) -> ResearchState | None:
        row = self.conn.execute(
            "SELECT state_json FROM research_states WHERE session_id=?", (session_id,)
        ).fetchone()
        return ResearchState.model_validate_json(row[0]) if row else None

    def record_gate(
        self,
        result: GateResult,
        *,
        session_id: str | None = None,
        paper_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO gate_runs(session_id,paper_id,gate_name,passed,score,result_json)
               VALUES(?,?,?,?,?,?)""",
            (session_id, paper_id, result.name, int(result.passed), result.score,
             result.model_dump_json()),
        )
        self.conn.commit()

    def evidence_ids_for_paper(self, paper_id: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT evidence_id FROM evidence WHERE paper_id=?", (paper_id,)
        ).fetchall()
        return {row[0] for row in rows}

    def search(self, query: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """SELECT p.*, bm25(paper_fts) AS rank FROM paper_fts
               JOIN papers p USING(canonical_id)
               WHERE paper_fts MATCH ? ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, int]:
        return {
            "papers": self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
            "claims": self.conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "evidence": self.conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "relations": self.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
            "analyses": self.conn.execute("SELECT COUNT(*) FROM paper_analysis").fetchone()[0],
            "critiques": self.conn.execute("SELECT COUNT(*) FROM paper_critiques").fetchone()[0],
            "sessions": self.conn.execute("SELECT COUNT(*) FROM research_states").fetchone()[0],
            "gate_runs": self.conn.execute("SELECT COUNT(*) FROM gate_runs").fetchone()[0],
        }
