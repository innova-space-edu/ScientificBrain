from __future__ import annotations

import os
from dataclasses import dataclass

from .discovery import OpenAlexClient
from .fulltext import FullTextDocument, extract_pdf_bytes, fetch_pdf, ingest_open_access_paper
from .memory import ScientificMemory
from .models import Paper, ReviewDepth
from .paper_memory import PaperMemoryStore
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

    def _paper_memory(self) -> PaperMemoryStore | None:
        user = getattr(self.snapshot_store, "user", None)
        folder_id = getattr(self.snapshot_store, "folder_id", None)
        if user is None or not folder_id:
            return None
        return PaperMemoryStore(user, str(folder_id))

    def load_document(self, paper_id: str, *, pdf_url: str | None = None) -> tuple[Paper, FullTextDocument]:
        """Resolve one PDF, persist its extracted pages once, and reuse them thereafter."""

        paper = self.memory.get_paper(paper_id) or self.load_cloud_paper(paper_id)
        cache = self._paper_memory()
        if cache:
            cached = cache.load_document(paper_id)
            if cached is not None:
                return paper, cached

        if pdf_url:
            data = fetch_pdf(pdf_url)
            document = extract_pdf_bytes(paper.canonical_id, pdf_url, data)
        else:
            private_fetch = getattr(self.snapshot_store, "fetch_paper_pdf", None)
            private_pdf = private_fetch(paper_id) if callable(private_fetch) else None
            if private_pdf:
                source_url, data = private_pdf
                document = extract_pdf_bytes(paper.canonical_id, source_url, data)
            else:
                document = ingest_open_access_paper(
                    paper,
                    unpaywall_email=os.getenv("UNPAYWALL_EMAIL"),
                )

        if cache:
            cache.save_document(document)
        return paper, document

    def review_paper(self, paper_id: str, *, pdf_url: str | None = None):
        paper, document = self.load_document(paper_id, pdf_url=pdf_url)
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

    def review_open_access_paper(self, paper_id: str):
        return self.review_paper(paper_id)
