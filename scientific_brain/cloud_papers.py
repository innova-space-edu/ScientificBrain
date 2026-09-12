from __future__ import annotations

import os
from dataclasses import dataclass

from .discovery import OpenAlexClient
from .fulltext import ingest_open_access_paper
from .memory import ScientificMemory
from .models import Paper, ReviewDepth
from .persistence import SnapshotStore
from .taxonomy import load_taxonomy
from .workflow import ScientificWorkflow


@dataclass
class CloudPaperService:
    memory: ScientificMemory
    provider: object
    snapshot_store: SnapshotStore

    def discover(
        self,
        query: str,
        *,
        from_year: int = 1900,
        max_results: int = 100,
        taxonomy_path: str = "config/plasma_taxonomy.yaml",
    ) -> list[Paper]:
        taxonomy = load_taxonomy(taxonomy_path)
        client = OpenAlexClient(
            taxonomy,
            mailto=os.getenv("OPENALEX_MAILTO") or os.getenv("UNPAYWALL_EMAIL"),
        )
        papers = client.search(query, from_year=from_year, per_page=max_results)
        for paper in papers:
            self.memory.upsert_paper(paper)
            self.snapshot_store.save_paper_bundle(paper)
        return papers

    def load_cloud_paper(self, paper_id: str) -> Paper:
        bundles = self.snapshot_store.load_paper_bundles([paper_id])
        if not bundles:
            raise KeyError(f"Paper not found in cloud memory: {paper_id}")
        paper = Paper.model_validate(bundles[0]["record"])
        self.memory.upsert_paper(paper)
        return paper

    def review_open_access_paper(self, paper_id: str):
        paper = self.memory.get_paper(paper_id) or self.load_cloud_paper(paper_id)
        document = ingest_open_access_paper(
            paper,
            unpaywall_email=os.getenv("UNPAYWALL_EMAIL"),
        )
        result = ScientificWorkflow(self.memory, self.provider).review_paper(
            paper_id,
            document.text,
            depth=ReviewDepth.FULL_TEXT,
            source_path=document.source_url,
        )
        updated_paper = self.memory.get_paper(paper_id) or paper
        self.snapshot_store.save_paper_bundle(
            updated_paper,
            result.analysis,
            result.critique,
            result.specialist_reviews,
        )
        return result, document
