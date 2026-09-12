from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from .auth import AuthenticatedUser, supabase_public_config


def _canonical_id(payload: dict[str, Any]) -> str:
    supplied = str(payload.get("canonical_id") or "").strip()
    if supplied:
        return supplied
    doi = str(payload.get("doi") or "").strip().lower().removeprefix("https://doi.org/")
    if doi:
        return f"doi:{doi}"
    arxiv_id = str(payload.get("arxiv_id") or "").strip()
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    return f"userdoc:{uuid.uuid4()}"


@dataclass
class UserWorkspaceStore:
    user: AuthenticatedUser
    timeout: float = 30.0

    def __post_init__(self) -> None:
        config = supabase_public_config()
        self.url = config["url"].rstrip("/")
        self.key = config["publishable_key"]
        if not self.url or not self.key:
            raise RuntimeError("Supabase public configuration is incomplete")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.user.access_token}",
            "Content-Type": "application/json",
        }

    def _endpoint(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = httpx.get(self._endpoint(table), headers=self.headers, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            self._endpoint(table),
            headers={**self.headers, "Prefer": "return=representation"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else payload

    def _patch(self, table: str, filters: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.patch(
            self._endpoint(table),
            headers={**self.headers, "Prefer": "return=representation"},
            params=filters,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else payload

    def _delete(self, table: str, filters: dict[str, str]) -> None:
        response = httpx.delete(self._endpoint(table), headers=self.headers, params=filters, timeout=self.timeout)
        response.raise_for_status()

    def list_folders(self) -> list[dict[str, Any]]:
        return self._select(
            "scibrain_folders",
            {
                "select": "folder_id,parent_id,name,year,research_line,area,description,paper_target,sort_order,created_at,updated_at",
                "order": "sort_order.asc,name.asc",
            },
        )

    def create_folder(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Folder name is required")
        row = {
            "owner_id": self.user.user_id,
            "parent_id": payload.get("parent_id"),
            "name": name,
            "year": payload.get("year"),
            "research_line": payload.get("research_line"),
            "area": payload.get("area"),
            "description": payload.get("description"),
            "paper_target": int(payload.get("paper_target") or 100),
            "sort_order": int(payload.get("sort_order") or 0),
        }
        return self._insert("scibrain_folders", row)

    def update_folder(self, folder_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"name", "parent_id", "year", "research_line", "area", "description", "paper_target", "sort_order"}
        row = {key: value for key, value in payload.items() if key in allowed}
        if "name" in row and not str(row["name"]).strip():
            raise ValueError("Folder name cannot be empty")
        return self._patch("scibrain_folders", {"folder_id": f"eq.{folder_id}"}, row)

    def delete_folder(self, folder_id: str) -> None:
        self._delete("scibrain_folders", {"folder_id": f"eq.{folder_id}"})

    def get_folder(self, folder_id: str) -> dict[str, Any] | None:
        rows = self._select(
            "scibrain_folders",
            {"folder_id": f"eq.{folder_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else None

    def list_papers(self, folder_id: str) -> list[dict[str, Any]]:
        return self._select(
            "scibrain_folder_papers",
            {
                "folder_id": f"eq.{folder_id}",
                "select": "item_id,folder_id,project_id,canonical_id,title,authors,publication_date,journal,doi,arxiv_id,source_type,source_url,pdf_url,access_status,manual_lookup_required,storage_path,original_filename,file_size_bytes,review_depth,created_at,updated_at",
                "order": "created_at.desc",
            },
        )

    def add_paper(self, folder_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("Paper title is required")
        canonical = _canonical_id(payload)
        source_url = payload.get("source_url") or payload.get("url")
        source_type = payload.get("source_type") or "manual"
        record = payload.get("record") or {
            "canonical_id": canonical,
            "title": title,
            "abstract": payload.get("abstract") or "",
            "authors": payload.get("authors") or [],
            "publication_date": payload.get("publication_date"),
            "journal": payload.get("journal"),
            "doi": payload.get("doi"),
            "arxiv_id": payload.get("arxiv_id"),
            "url": source_url,
            "cited_by_count": int(payload.get("cited_by_count") or 0),
            "plasma_topics": payload.get("plasma_topics") or [],
            "source": source_type,
        }
        row = {
            "owner_id": self.user.user_id,
            "folder_id": folder_id,
            "project_id": payload.get("project_id"),
            "canonical_id": canonical,
            "title": title,
            "authors": payload.get("authors") or [],
            "publication_date": payload.get("publication_date"),
            "journal": payload.get("journal"),
            "doi": payload.get("doi"),
            "arxiv_id": payload.get("arxiv_id"),
            "source_type": source_type,
            "source_url": source_url,
            "pdf_url": payload.get("pdf_url"),
            "access_status": payload.get("access_status") or "metadata_only",
            "manual_lookup_required": bool(payload.get("manual_lookup_required", False)),
            "storage_path": payload.get("storage_path"),
            "original_filename": payload.get("original_filename"),
            "mime_type": payload.get("mime_type"),
            "file_size_bytes": payload.get("file_size_bytes"),
            "review_depth": payload.get("review_depth") or "metadata_verified",
            "record": record,
            "notes": payload.get("notes"),
        }
        return self._insert("scibrain_folder_papers", row)

    def update_paper(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "project_id", "title", "authors", "publication_date", "journal", "doi", "arxiv_id",
            "source_url", "pdf_url", "access_status", "manual_lookup_required", "storage_path",
            "original_filename", "mime_type", "file_size_bytes", "review_depth", "record", "analysis",
            "critique", "specialist_reviews", "notes",
        }
        return self._patch(
            "scibrain_folder_papers",
            {"item_id": f"eq.{item_id}"},
            {key: value for key, value in payload.items() if key in allowed},
        )

    def delete_paper(self, item_id: str) -> None:
        self._delete("scibrain_folder_papers", {"item_id": f"eq.{item_id}"})

    def save_search(self, folder_id: str, query: str, sources: list[str], results: list[dict[str, Any]], project_id: str | None = None) -> dict[str, Any]:
        return self._insert(
            "scibrain_research_searches",
            {
                "owner_id": self.user.user_id,
                "folder_id": folder_id,
                "project_id": project_id,
                "query": query,
                "sources": sources,
                "result_count": len(results),
                "results": results,
            },
        )

    def new_storage_path(self, folder_id: str, filename: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in filename).strip("._") or "paper.pdf"
        return f"{self.user.user_id}/{folder_id}/{uuid.uuid4().hex}-{safe}"
