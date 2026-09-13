from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .auth import AuthenticatedUser, supabase_public_config
from .bounded_search import BoundedResearchSearchService
from .usage import UsageRecorder
from .workspaces import UserWorkspaceStore


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def result_key(row: dict[str, Any]) -> str:
    doi = _clean(row.get("doi"))
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    if doi:
        return f"doi:{doi}"
    arxiv = _clean(row.get("arxiv_id"))
    if arxiv:
        return f"arxiv:{arxiv}"
    title = re.sub(r"[^a-z0-9]+", "", _clean(row.get("title")))
    if title:
        return f"title:{title[:220]}"
    url = _clean(row.get("url") or row.get("source_url") or row.get("public_url"))
    return f"url:{url}" if url else "unknown:"


def _hash_keys(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(set(keys))).encode("utf-8")).hexdigest()[:24]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LiteratureWatchService:
    user: AuthenticatedUser
    folder_id: str

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)
        self.usage = UsageRecorder(self.user, self.folder_id)

    def list_watches(self) -> list[dict[str, Any]]:
        return self.workspace._select(
            "scibrain_literature_watches",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

    def create_watch(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        return self.workspace._insert(
            "scibrain_literature_watches",
            {
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "query": query,
                "from_year": max(1800, min(int(payload.get("from_year") or 1900), 2100)),
                "max_results": max(1, min(int(payload.get("max_results") or 30), 40)),
                "include_web": bool(payload.get("include_web", True)),
                "enabled": bool(payload.get("enabled", True)),
                "interval_hours": max(1, min(int(payload.get("interval_hours") or 24), 720)),
                "updated_at": _iso_now(),
            },
        )

    def update_watch(self, watch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed: dict[str, Any] = {}
        if "query" in payload:
            query = str(payload.get("query") or "").strip()
            if not query:
                raise ValueError("query cannot be empty")
            allowed["query"] = query
        if "enabled" in payload:
            allowed["enabled"] = bool(payload.get("enabled"))
        if "include_web" in payload:
            allowed["include_web"] = bool(payload.get("include_web"))
        if "from_year" in payload:
            allowed["from_year"] = max(1800, min(int(payload.get("from_year") or 1900), 2100))
        if "max_results" in payload:
            allowed["max_results"] = max(1, min(int(payload.get("max_results") or 30), 40))
        if "interval_hours" in payload:
            allowed["interval_hours"] = max(1, min(int(payload.get("interval_hours") or 24), 720))
        allowed["updated_at"] = _iso_now()
        return self.workspace._patch(
            "scibrain_literature_watches",
            {"watch_id": f"eq.{watch_id}", "folder_id": f"eq.{self.folder_id}"},
            allowed,
        )

    def list_runs(self, watch_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        params = {
            "folder_id": f"eq.{self.folder_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(max(1, min(int(limit), 100))),
        }
        if watch_id:
            params["watch_id"] = f"eq.{watch_id}"
        return self.workspace._select("scibrain_literature_watch_runs", params)

    def _watch(self, watch_id: str) -> dict[str, Any]:
        rows = self.workspace._select(
            "scibrain_literature_watches",
            {
                "watch_id": f"eq.{watch_id}",
                "folder_id": f"eq.{self.folder_id}",
                "select": "*",
                "limit": "1",
            },
        )
        if not rows:
            raise KeyError("literature_watch_not_found")
        return rows[0]

    def _existing_keys(self) -> set[str]:
        return {result_key(row) for row in self.workspace.list_papers(self.folder_id)}

    def run_watch(self, watch_id: str) -> dict[str, Any]:
        watch = self._watch(watch_id)
        started = time.perf_counter()
        try:
            result = BoundedResearchSearchService().search(
                str(watch.get("query") or ""),
                from_year=int(watch.get("from_year") or 1900),
                max_results=max(1, min(int(watch.get("max_results") or 30), 40)),
                include_web=bool(watch.get("include_web", True)),
                resolve_open_access=True,
            )
            rows = result.get("results") or []
            existing = self._existing_keys()
            seen = {str(x) for x in (watch.get("seen_keys") or [])}
            keyed = [(result_key(row), row) for row in rows]
            new_results = [row for key, row in keyed if key not in existing and key not in seen and key != "unknown:"]
            all_keys = [key for key, _ in keyed if key != "unknown:"]
            merged_seen = list(dict.fromkeys(list(seen) + all_keys))[-2000:]
            result_hash = _hash_keys(all_keys)
            duration_ms = int((time.perf_counter() - started) * 1000)
            run = self.workspace._insert(
                "scibrain_literature_watch_runs",
                {
                    "watch_id": watch_id,
                    "owner_id": self.user.user_id,
                    "folder_id": self.folder_id,
                    "query": watch.get("query"),
                    "result_count": len(rows),
                    "new_count": len(new_results),
                    "new_results": new_results,
                    "sources": result.get("sources") or [],
                    "errors": result.get("errors") or [],
                    "result_hash": result_hash,
                    "duration_ms": duration_ms,
                },
            )
            updated = self.workspace._patch(
                "scibrain_literature_watches",
                {"watch_id": f"eq.{watch_id}"},
                {
                    "seen_keys": merged_seen,
                    "last_checked_at": _iso_now(),
                    "last_new_count": len(new_results),
                    "last_result_hash": result_hash,
                    "last_error": None,
                    "updated_at": _iso_now(),
                },
            )
            self.usage.record(
                "literature_watch_run",
                duration_ms=duration_ms,
                metadata={"watch_id": watch_id, "results": len(rows), "new": len(new_results)},
            )
            return {"watch": updated, "run": run, "new_results": new_results, "search": result}
        except Exception as exc:
            try:
                self.workspace._patch(
                    "scibrain_literature_watches",
                    {"watch_id": f"eq.{watch_id}"},
                    {"last_checked_at": _iso_now(), "last_error": f"{type(exc).__name__}: {exc}", "updated_at": _iso_now()},
                )
            except Exception:
                pass
            raise


class LiteratureWatchCronRunner:
    """Service-role runner for Vercel Cron. Processes only a small due batch per invocation."""

    def __init__(self) -> None:
        config = supabase_public_config()
        self.url = config["url"].rstrip("/")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not self.url or not self.service_key:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for autonomous literature watch")
        self.headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }

    def _endpoint(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = httpx.get(self._endpoint(table), headers=self.headers, params=params, timeout=30.0)
        response.raise_for_status()
        return response.json()

    def _patch(self, table: str, filters: dict[str, str], payload: dict[str, Any]) -> None:
        response = httpx.patch(self._endpoint(table), headers=self.headers, params=filters, json=payload, timeout=30.0)
        response.raise_for_status()

    def _insert(self, table: str, payload: dict[str, Any]) -> None:
        response = httpx.post(self._endpoint(table), headers=self.headers, json=payload, timeout=30.0)
        response.raise_for_status()

    def _existing_keys(self, owner_id: str, folder_id: str) -> set[str]:
        rows = self._get(
            "scibrain_folder_papers",
            {
                "owner_id": f"eq.{owner_id}",
                "folder_id": f"eq.{folder_id}",
                "select": "canonical_id,title,doi,arxiv_id,source_url",
                "limit": "2000",
            },
        )
        return {result_key(row) for row in rows}

    def due_watches(self, limit: int = 2) -> list[dict[str, Any]]:
        rows = self._get(
            "scibrain_literature_watches",
            {
                "enabled": "eq.true",
                "select": "*",
                "order": "last_checked_at.asc.nullsfirst",
                "limit": "30",
            },
        )
        now = datetime.now(timezone.utc)
        due: list[dict[str, Any]] = []
        for row in rows:
            last = row.get("last_checked_at")
            interval = max(1, int(row.get("interval_hours") or 24))
            if not last:
                due.append(row)
            else:
                try:
                    parsed = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                    if parsed + timedelta(hours=interval) <= now:
                        due.append(row)
                except ValueError:
                    due.append(row)
            if len(due) >= max(1, min(int(limit), 3)):
                break
        return due

    def run_due(self, limit: int = 2) -> dict[str, Any]:
        processed: list[dict[str, Any]] = []
        for watch in self.due_watches(limit):
            watch_id = str(watch["watch_id"])
            owner_id = str(watch["owner_id"])
            folder_id = str(watch["folder_id"])
            started = time.perf_counter()
            try:
                result = BoundedResearchSearchService().search(
                    str(watch.get("query") or ""),
                    from_year=int(watch.get("from_year") or 1900),
                    max_results=max(1, min(int(watch.get("max_results") or 30), 40)),
                    include_web=bool(watch.get("include_web", True)),
                    resolve_open_access=True,
                )
                rows = result.get("results") or []
                existing = self._existing_keys(owner_id, folder_id)
                seen = {str(x) for x in (watch.get("seen_keys") or [])}
                keyed = [(result_key(row), row) for row in rows]
                new_results = [row for key, row in keyed if key not in existing and key not in seen and key != "unknown:"]
                all_keys = [key for key, _ in keyed if key != "unknown:"]
                result_hash = _hash_keys(all_keys)
                duration_ms = int((time.perf_counter() - started) * 1000)
                self._insert(
                    "scibrain_literature_watch_runs",
                    {
                        "watch_id": watch_id,
                        "owner_id": owner_id,
                        "folder_id": folder_id,
                        "query": watch.get("query"),
                        "result_count": len(rows),
                        "new_count": len(new_results),
                        "new_results": new_results,
                        "sources": result.get("sources") or [],
                        "errors": result.get("errors") or [],
                        "result_hash": result_hash,
                        "duration_ms": duration_ms,
                    },
                )
                merged_seen = list(dict.fromkeys(list(seen) + all_keys))[-2000:]
                self._patch(
                    "scibrain_literature_watches",
                    {"watch_id": f"eq.{watch_id}"},
                    {
                        "seen_keys": merged_seen,
                        "last_checked_at": _iso_now(),
                        "last_new_count": len(new_results),
                        "last_result_hash": result_hash,
                        "last_error": None,
                        "updated_at": _iso_now(),
                    },
                )
                processed.append({"watch_id": watch_id, "status": "ok", "new": len(new_results), "results": len(rows)})
            except Exception as exc:
                try:
                    self._patch(
                        "scibrain_literature_watches",
                        {"watch_id": f"eq.{watch_id}"},
                        {"last_checked_at": _iso_now(), "last_error": f"{type(exc).__name__}: {exc}", "updated_at": _iso_now()},
                    )
                except Exception:
                    pass
                processed.append({"watch_id": watch_id, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
        return {"processed": processed, "count": len(processed)}
