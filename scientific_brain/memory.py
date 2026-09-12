from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Claim, Evidence, Paper


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
"""


class ScientificMemory:
    def __init__(self, path: str | Path = "scientific_brain.db") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

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
              kind=excluded.kind, topics_json=excluded.topics_json, source=excluded.source""",
            payload,
        )
        self.conn.execute("DELETE FROM paper_fts WHERE canonical_id=?", (paper.canonical_id,))
        self.conn.execute(
            "INSERT INTO paper_fts(canonical_id,title,abstract,topics) VALUES(?,?,?,?)",
            (paper.canonical_id, paper.title, paper.abstract, " ".join(paper.plasma_topics)),
        )
        self.conn.commit()

    def add_evidence(self, item: Evidence) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO evidence VALUES(?,?,?,?,?,?,?,?)",
            (item.evidence_id, item.paper_id, item.text, item.section, item.page,
             item.equation, item.figure, item.strength.value),
        )
        self.conn.commit()

    def add_claim(self, claim: Claim) -> None:
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
        }
