from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .auth import AuthenticatedUser
from .workspaces import UserWorkspaceStore


@dataclass
class ScientificObservabilityService:
    user: AuthenticatedUser
    folder_id: str

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)

    def _embedding_stats(self) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.workspace.url}/rest/v1/rpc/scibrain_folder_embedding_stats",
                headers=self.workspace.headers,
                json={"p_folder_id": self.folder_id},
                timeout=self.workspace.timeout,
            )
            response.raise_for_status()
            rows = response.json()
            return rows[0] if rows else {}
        except Exception:
            return {}

    def _benchmark_runs(self, since: str) -> list[dict[str, Any]]:
        try:
            return self.workspace._select(
                "scibrain_benchmark_runs",
                {
                    "folder_id": f"eq.{self.folder_id}",
                    "created_at": f"gte.{since}",
                    "select": "run_id,document_id,revision,benchmark_type,score,metrics,findings,created_at",
                    "order": "created_at.desc",
                    "limit": "100",
                },
            )
        except Exception:
            return []

    def snapshot(self, days: int = 7) -> dict[str, Any]:
        days = max(1, min(int(days), 30))
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        events = self.workspace._select(
            "scibrain_usage_events",
            {
                "folder_id": f"eq.{self.folder_id}",
                "created_at": f"gte.{since}",
                "select": "event_type,duration_ms,metadata,created_at",
                "order": "created_at.desc",
                "limit": "1500",
            },
        )
        jobs = self.workspace._select(
            "scibrain_jobs",
            {
                "folder_id": f"eq.{self.folder_id}",
                "created_at": f"gte.{since}",
                "select": "job_id,job_type,status,progress,last_error,created_at,updated_at",
                "order": "created_at.desc",
                "limit": "500",
            },
        )
        watches = self.workspace._select(
            "scibrain_literature_watches",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "watch_id,enabled,last_checked_at,last_new_count,last_error",
                "limit": "100",
            },
        )
        papers = self.workspace.list_papers(self.folder_id)
        embedding = self._embedding_stats()
        benchmarks = self._benchmark_runs(since)

        event_counts = Counter(str(row.get("event_type") or "unknown") for row in events)
        durations: dict[str, list[int]] = defaultdict(list)
        token_totals = {"input": 0, "output": 0, "total": 0, "cached": 0, "reasoning": 0}
        provider_counts = Counter()
        model_counts = Counter()
        ai_events = 0
        exact_usage_events = 0
        cost_events = 0
        provider_reported_cost = 0.0
        configured_cost = 0.0
        total_cost = 0.0

        for row in events:
            event = str(row.get("event_type") or "unknown")
            if row.get("duration_ms") is not None:
                try:
                    durations[event].append(int(row.get("duration_ms") or 0))
                except (TypeError, ValueError):
                    pass
            metadata = row.get("metadata") or {}
            if event == "ai_completion":
                ai_events += 1
                if metadata.get("usage_exact") is True:
                    exact_usage_events += 1
                provider = str(metadata.get("provider") or "unknown")
                model = str(metadata.get("model") or "unknown")
                provider_counts[provider] += 1
                model_counts[model] += 1
            for key, dest in (
                ("input_tokens", "input"),
                ("output_tokens", "output"),
                ("total_tokens", "total"),
                ("cached_input_tokens", "cached"),
                ("reasoning_tokens", "reasoning"),
            ):
                try:
                    token_totals[dest] += int(metadata.get(key) or 0)
                except (TypeError, ValueError):
                    pass
            raw_cost = metadata.get("cost_usd")
            if raw_cost is None:
                raw_cost = metadata.get("estimated_cost_usd")
            try:
                if raw_cost is not None:
                    value = float(raw_cost or 0.0)
                    total_cost += value
                    cost_events += 1
                    if metadata.get("cost_source") == "provider_reported":
                        provider_reported_cost += value
                    elif metadata.get("cost_source") == "configured_rate":
                        configured_cost += value
            except (TypeError, ValueError):
                pass

        latency = {
            event: {
                "avg_ms": round(sum(values) / len(values), 1),
                "max_ms": max(values),
                "samples": len(values),
            }
            for event, values in durations.items()
            if values
        }
        job_status = Counter(str(row.get("status") or "unknown") for row in jobs)
        retry_count = 0
        phase_errors = Counter()
        recent_errors: list[dict[str, Any]] = []
        for row in jobs:
            progress = row.get("progress") or {}
            history = progress.get("error_history") or []
            retry_count += len(history)
            for item in history:
                phase_errors[str((item or {}).get("phase") or "unknown")] += 1
            if row.get("last_error"):
                recent_errors.append({
                    "job_id": row.get("job_id"),
                    "job_type": row.get("job_type"),
                    "status": row.get("status"),
                    "error": row.get("last_error"),
                    "updated_at": row.get("updated_at"),
                })

        chunk_count = int(embedding.get("chunk_count") or 0)
        embedded_chunks = int(embedding.get("embedded_chunks") or 0)
        full_text = sum(row.get("review_depth") == "full_text_reviewed" for row in papers)
        readable = sum(bool(row.get("system_can_read")) for row in papers)
        watch_errors = [w for w in watches if w.get("last_error")]
        latest_benchmark = benchmarks[0] if benchmarks else {}
        latest_metrics = latest_benchmark.get("metrics") or {}

        return {
            "window_days": days,
            "corpus": {
                "papers": len(papers),
                "full_text_reviewed": full_text,
                "readable": readable,
                "indexed_papers": int(embedding.get("paper_count") or 0),
                "chunks": chunk_count,
                "embedded_chunks": embedded_chunks,
                "embedding_coverage": (embedded_chunks / chunk_count) if chunk_count else 0.0,
                "fully_embedded_papers": int(embedding.get("fully_embedded_papers") or 0),
            },
            "autonomy": {
                "jobs": len(jobs),
                "job_status": dict(job_status),
                "retries_recorded": retry_count,
                "phase_error_counts": dict(phase_errors),
                "active_literature_watches": sum(bool(w.get("enabled")) for w in watches),
                "watch_new_items_last_runs": sum(int(w.get("last_new_count") or 0) for w in watches),
                "watch_errors": len(watch_errors),
            },
            "usage": {
                "events": len(events),
                "event_counts": dict(event_counts),
                "latency": latency,
                "ai_completion_events": ai_events,
                "exact_usage_events": exact_usage_events,
                "exact_usage_coverage": (exact_usage_events / ai_events) if ai_events else 0.0,
                "input_tokens_recorded": token_totals["input"],
                "output_tokens_recorded": token_totals["output"],
                "total_tokens_recorded": token_totals["total"] or token_totals["input"] + token_totals["output"],
                "cached_input_tokens_recorded": token_totals["cached"],
                "reasoning_tokens_recorded": token_totals["reasoning"],
                "provider_counts": dict(provider_counts),
                "model_counts": dict(model_counts),
                "known_cost_usd": round(total_cost, 8) if cost_events else None,
                "provider_reported_cost_usd": round(provider_reported_cost, 8) if provider_reported_cost else None,
                "configured_rate_cost_usd": round(configured_cost, 8) if configured_cost else None,
                "cost_samples": cost_events,
                "cost_tracking_complete": bool(ai_events) and cost_events == ai_events,
                "cost_tracking_note": "Costs are recorded only when the provider reports them or SCIBRAIN_MODEL_PRICING_JSON supplies a rate.",
            },
            "quality": {
                "corpus_answers": event_counts.get("corpus_question_answered", 0),
                "semantic_corpus_searches": event_counts.get("semantic_corpus_search", 0),
                "semantic_paper_searches": event_counts.get("semantic_paper_search", 0),
                "ocr_pages": event_counts.get("ocr_page", 0),
                "visual_pages": event_counts.get("visual_page_analysis", 0),
                "benchmark_runs": len(benchmarks),
                "latest_benchmark_score": latest_benchmark.get("score"),
                "latest_entailment_rate": latest_metrics.get("entailment_rate"),
                "latest_unsupported_rate": latest_metrics.get("unsupported_rate"),
                "latest_hallucination_risk_index": latest_metrics.get("hallucination_risk_index"),
            },
            "recent_errors": recent_errors[:12],
        }
