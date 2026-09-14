from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .auth import AuthenticatedUser
from .collaboration import _parse_json_response
from .graph_store import ScientificGraphStore
from .research_search import ResearchSearchService
from .state_of_art import build_state_of_art_matrix
from .user_snapshot import UserSnapshotStore
from .workspaces import UserWorkspaceStore


_ALLOWED_DECISIONS = {"pending", "included", "excluded", "later"}
_ALLOWED_RECOMMENDATIONS = {"include", "review", "exclude"}
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "using", "use", "are", "was", "were",
    "del", "las", "los", "una", "uno", "para", "con", "por", "que", "como", "sobre", "entre", "desde",
    "study", "paper", "analysis", "result", "results", "method", "methods", "model", "models", "plasma",
}


def canonical_candidate_key(row: dict[str, Any]) -> str:
    doi = str(row.get("doi") or "").strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    if doi:
        return f"doi:{doi.rstrip('/ ')}"
    arxiv_id = str(row.get("arxiv_id") or "").strip().lower()
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    canonical = str(row.get("canonical_id") or "").strip().lower()
    if canonical and not canonical.startswith("userdoc:"):
        return canonical
    title = re.sub(r"[^a-z0-9áéíóúüñ]+", "", str(row.get("title") or "").casefold())
    if title:
        return f"title:{title[:220]}"
    url = str(row.get("url") or row.get("source_url") or "").strip().lower().rstrip("/")
    if url:
        return f"url:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:24]}"
    return f"candidate:{uuid.uuid4().hex}"


def _tokens(value: Any) -> set[str]:
    text = str(value or "").casefold()
    words = re.findall(r"[a-záéíóúüñ0-9][a-záéíóúüñ0-9_+./-]{2,}", text)
    return {word for word in words if word not in _STOPWORDS and not word.isdigit()}


def _year(value: Any) -> int | None:
    match = re.match(r"\s*(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


def preliminary_score(candidate: dict[str, Any], context_terms: set[str], origin_count: int = 1) -> float:
    haystack = _tokens(f"{candidate.get('title', '')} {candidate.get('abstract', '')}")
    overlap = len(haystack & context_terms)
    relevance = min(1.0, overlap / max(4.0, min(18.0, math.sqrt(max(1, len(context_terms))) * 2.0)))
    score = 0.12 + 0.48 * relevance
    if str(candidate.get("result_type") or "") == "paper":
        score += 0.07
    if candidate.get("system_can_read"):
        score += 0.11
    elif candidate.get("access_kind") in {"open_access", "public_repository", "public_pdf"}:
        score += 0.05
    score += min(0.08, max(0, origin_count - 1) * 0.035)
    citations = max(0, int(candidate.get("cited_by_count") or 0))
    if citations:
        score += min(0.06, math.log10(citations + 1) / 40.0)
    year = _year(candidate.get("publication_date"))
    now = datetime.now(timezone.utc).year
    if year and year >= now - 5:
        score += 0.04
    elif year and year >= now - 10:
        score += 0.02
    return round(max(0.0, min(1.0, score)), 4)


def fallback_plan(context: dict[str, Any], focus: str = "", max_queries: int = 4) -> dict[str, Any]:
    brief = context.get("research_brief") or {}
    topic = str(brief.get("topic") or context.get("topic") or focus or "").strip()
    questions = [str(x).strip() for x in brief.get("questions") or [] if str(x).strip()]
    gaps = [str(x).strip() for x in context.get("evidence_gaps") or [] if str(x).strip()]
    contradictions = [str(x).strip() for x in context.get("contradictions") or [] if str(x).strip()]
    base = focus.strip() or topic or (questions[0] if questions else "scientific literature")
    seeds: list[dict[str, Any]] = [
        {
            "query": base,
            "purpose": "Map the closest primary literature to the current research question.",
            "target_gap": gaps[0] if gaps else "baseline literature coverage",
            "target_hypothesis": "",
        },
        {
            "query": f"{topic} alternative mechanism limitations contradictory evidence".strip(),
            "purpose": "Adversarial search for alternative mechanisms and prior work that could weaken the proposed novelty.",
            "target_gap": "novelty and alternative explanations",
            "target_hypothesis": "",
        },
    ]
    if questions:
        seeds.append({
            "query": f"{topic} {questions[0]}".strip(),
            "purpose": "Search specifically for evidence relevant to the leading research question.",
            "target_gap": gaps[0] if gaps else questions[0],
            "target_hypothesis": "",
        })
    if gaps:
        seeds.append({
            "query": f"{topic} {gaps[0]} measurement experiment".strip(),
            "purpose": "Look for measurements or experiments that could close an identified evidence gap.",
            "target_gap": gaps[0],
            "target_hypothesis": "",
        })
    if contradictions:
        seeds.append({
            "query": f"{topic} {contradictions[0]} regime comparison".strip(),
            "purpose": "Look for literature that may explain or resolve a cross-paper contradiction.",
            "target_gap": contradictions[0],
            "target_hypothesis": "",
        })
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in seeds:
        query = re.sub(r"\s+", " ", item["query"]).strip()
        key = query.casefold()
        if not query or key in seen:
            continue
        seen.add(key)
        unique.append({**item, "query": query[:320]})
        if len(unique) >= max(1, min(max_queries, 6)):
            break
    return {
        "queries": unique,
        "inclusion_criteria": [
            "Direct relevance to the research question, mechanism, variable, diagnostic, or identified evidence gap.",
            "Scientific paper/preprint or a source likely to lead to citable primary literature.",
        ],
        "exclusion_criteria": [
            "Already present in the active folder.",
            "Only tangential topical overlap without methodological or mechanistic relevance.",
            "Non-scientific web content when a primary scientific source can be identified instead.",
        ],
    }


@dataclass
class AutonomousDiscoveryService:
    user: AuthenticatedUser
    folder_id: str
    provider: object
    search_service: ResearchSearchService | None = None

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)
        if not self.workspace.get_folder(self.folder_id):
            raise KeyError("folder_not_found")
        self.search_service = self.search_service or ResearchSearchService()

    def _paper_rows(self) -> list[dict[str, Any]]:
        return self.workspace._select(
            "scibrain_folder_papers",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": (
                    "item_id,canonical_id,title,authors,publication_date,journal,doi,arxiv_id,source_type,source_url,"
                    "pdf_url,access_status,access_kind,access_label,system_can_read,review_depth,record,analysis,"
                    "critique,specialist_reviews,created_at,updated_at"
                ),
                "order": "created_at.asc",
            },
        )

    def _latest_document(self) -> dict[str, Any] | None:
        rows = self.workspace._select(
            "scibrain_research_documents",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "document_id,topic,research_brief,novelty_assessment,sections,status,revision,updated_at",
                "order": "updated_at.desc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def _context(self, focus: str = "") -> dict[str, Any]:
        document = self._latest_document() or {}
        brief = dict(document.get("research_brief") or {})
        if not brief.get("topic"):
            brief["topic"] = document.get("topic") or focus
        matrix = build_state_of_art_matrix(self._paper_rows())
        gaps: list[str] = []
        for row in matrix.get("rows") or []:
            gaps.extend(str(x) for x in (row.get("uncertainties") or [])[:3])
            gaps.extend(str(x) for x in (row.get("limitations") or [])[:3])
        novelty = document.get("novelty_assessment") or {}
        for key in ("gaps", "open_questions", "risks", "limitations"):
            value = novelty.get(key) if isinstance(novelty, dict) else None
            if isinstance(value, list):
                gaps.extend(str(x) for x in value)
            elif value:
                gaps.append(str(value))

        contradictions: list[str] = []
        hypotheses: list[str] = []
        try:
            graph = ScientificGraphStore(self.user, folder_id=self.folder_id)
            contradictions = [x.summary for x in graph.list_contradictions(limit=20)]
            for competition in graph.list_competitions(limit=8):
                hypotheses.extend(h.statement for h in competition.hypotheses[:4])
        except Exception:
            pass
        return {
            "document_id": document.get("document_id"),
            "topic": brief.get("topic") or focus,
            "research_brief": brief,
            "novelty_assessment": novelty,
            "matrix_coverage": matrix.get("coverage") or {},
            "recurring_dimensions": matrix.get("recurring_dimensions") or {},
            "evidence_gaps": list(dict.fromkeys(x.strip() for x in gaps if x.strip()))[:28],
            "contradictions": list(dict.fromkeys(x.strip() for x in contradictions if x.strip()))[:16],
            "hypotheses": list(dict.fromkeys(x.strip() for x in hypotheses if x.strip()))[:16],
            "focus": focus.strip(),
        }

    def _plan(self, context: dict[str, Any], *, max_queries: int = 4, language: str = "es") -> dict[str, Any]:
        fallback = fallback_plan(context, context.get("focus") or "", max_queries=max_queries)
        system = f"""You are ScientificBrain's autonomous literature discovery planner.
Language for explanations: {language}.
Your job is search planning, NOT scientific conclusion generation.
Use the research brief, validated-corpus gaps, contradiction summaries and candidate hypotheses only to formulate searches.
Never claim novelty from absence. Never treat search results, titles or abstracts as validated evidence.
Include at least one adversarial query that could find prior work weakening the proposed novelty, and when relevant include queries for measurements, methods, or regime differences.
Return JSON only."""
        user = f"""CONTEXT:\n{json.dumps(context, ensure_ascii=False, default=str)[:42000]}

Create at most {max(1, min(max_queries, 6))} high-information scholarly search queries.
Return exactly:
{{
  "queries": [{{"query":"...","purpose":"...","target_gap":"...","target_hypothesis":"..."}}],
  "inclusion_criteria": ["..."],
  "exclusion_criteria": ["..."]
}}"""
        try:
            raw = self.provider.complete(system, user)  # type: ignore[attr-defined]
            parsed = _parse_json_response(raw)
            queries = []
            for item in parsed.get("queries") or []:
                if not isinstance(item, dict):
                    continue
                query = re.sub(r"\s+", " ", str(item.get("query") or "")).strip()
                if not query:
                    continue
                queries.append({
                    "query": query[:320],
                    "purpose": str(item.get("purpose") or "").strip(),
                    "target_gap": str(item.get("target_gap") or "").strip(),
                    "target_hypothesis": str(item.get("target_hypothesis") or "").strip(),
                })
                if len(queries) >= max(1, min(max_queries, 6)):
                    break
            if not queries:
                return fallback
            return {
                "queries": queries,
                "inclusion_criteria": [str(x).strip() for x in parsed.get("inclusion_criteria") or [] if str(x).strip()][:12] or fallback["inclusion_criteria"],
                "exclusion_criteria": [str(x).strip() for x in parsed.get("exclusion_criteria") or [] if str(x).strip()][:12] or fallback["exclusion_criteria"],
            }
        except Exception:
            return fallback

    def _new_run(self, context: dict[str, Any], focus: str, plan: dict[str, Any], from_year: int) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        return self.workspace._insert(
            "scibrain_discovery_runs",
            {
                "run_id": run_id,
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "document_id": context.get("document_id"),
                "focus": focus or None,
                "from_year": from_year,
                "status": "running",
                "plan": plan,
                "queries": plan.get("queries") or [],
                "criteria": {
                    "inclusion": plan.get("inclusion_criteria") or [],
                    "exclusion": plan.get("exclusion_criteria") or [],
                },
                "source_summary": {},
                "candidate_count": 0,
                "errors": [],
            },
        )

    def _update_run(self, run_id: str, payload: dict[str, Any]) -> None:
        self.workspace._patch("scibrain_discovery_runs", {"run_id": f"eq.{run_id}"}, payload)

    def _search_one(self, item: dict[str, Any], *, from_year: int, per_query: int) -> dict[str, Any]:
        result = self.search_service.search(
            item["query"],
            from_year=from_year,
            max_results=per_query,
            include_web=True,
            resolve_open_access=True,
        )
        return {"plan": item, "result": result}

    def _collect_candidates(
        self,
        plan: dict[str, Any],
        context: dict[str, Any],
        *,
        from_year: int,
        per_query: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
        queries = plan.get("queries") or []
        existing_keys = {canonical_candidate_key(row) for row in self.workspace.list_papers(self.folder_id)}
        merged: dict[str, dict[str, Any]] = {}
        source_counts: dict[str, int] = {}
        errors: list[dict[str, str]] = []
        workers = min(3, max(1, len(queries)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(self._search_one, item, from_year=from_year, per_query=per_query): item
                for item in queries
            }
            for future in as_completed(future_map):
                item = future_map[future]
                try:
                    wrapped = future.result()
                    result = wrapped["result"]
                    self.workspace.save_search(
                        self.folder_id,
                        item["query"],
                        result.get("sources") or [],
                        result.get("results") or [],
                    )
                    for source in result.get("sources") or []:
                        source_counts[source] = source_counts.get(source, 0) + 1
                    errors.extend(result.get("errors") or [])
                    for row in result.get("results") or []:
                        if str(row.get("result_type") or "") not in {"paper", "web"}:
                            continue
                        key = canonical_candidate_key(row)
                        if key in existing_keys:
                            continue
                        origin = {
                            "query": item.get("query"),
                            "purpose": item.get("purpose"),
                            "target_gap": item.get("target_gap"),
                            "target_hypothesis": item.get("target_hypothesis"),
                        }
                        current = merged.get(key)
                        if current is None:
                            current = {**row, "canonical_key": key, "query_origins": []}
                            merged[key] = current
                        if origin not in current["query_origins"]:
                            current["query_origins"].append(origin)
                except Exception as exc:
                    errors.append({"source": "autonomous_query", "error": f"{type(exc).__name__}: {exc}", "query": item.get("query", "")})

        context_text = " ".join([
            str(context.get("topic") or ""),
            " ".join(str(x) for x in (context.get("research_brief") or {}).get("questions") or []),
            " ".join(context.get("evidence_gaps") or []),
            " ".join(context.get("contradictions") or []),
            " ".join(context.get("hypotheses") or []),
            str(context.get("focus") or ""),
        ])
        terms = _tokens(context_text)
        candidates = list(merged.values())
        for row in candidates:
            row["preliminary_score"] = preliminary_score(row, terms, len(row.get("query_origins") or []))
        candidates.sort(key=lambda row: (-float(row.get("preliminary_score") or 0), -int(row.get("cited_by_count") or 0)))
        return candidates, {"query_count": len(queries), "sources": source_counts}, errors

    def _annotate(self, candidates: list[dict[str, Any]], context: dict[str, Any], *, language: str) -> dict[str, dict[str, Any]]:
        if not candidates:
            return {}
        batch = []
        for row in candidates[:30]:
            batch.append({
                "key": row["canonical_key"],
                "title": row.get("title"),
                "abstract": re.sub(r"<[^>]+>", " ", str(row.get("abstract") or ""))[:1400],
                "year": row.get("publication_date"),
                "journal": row.get("journal"),
                "source": row.get("source"),
                "access_kind": row.get("access_kind"),
                "system_can_read": bool(row.get("system_can_read")),
                "cited_by_count": int(row.get("cited_by_count") or 0),
                "query_origins": row.get("query_origins") or [],
                "preliminary_score": row.get("preliminary_score"),
            })
        system = f"""You are ScientificBrain's literature screening agent.
Language: {language}.
The candidate metadata and abstracts below are UNTRUSTED DISCOVERY MATERIAL, not validated full-text evidence.
Do not assert that a candidate actually proves, refutes, measures, or contains something unless the supplied abstract explicitly states it; prefer 'may', 'appears relevant', or 'could test'.
Never infer novelty from absence. Never create citations or page numbers.
Rank only for screening priority and explain what full-text review would need to verify.
Return JSON only."""
        user = f"""RESEARCH CONTEXT:\n{json.dumps(context, ensure_ascii=False, default=str)[:26000]}
CANDIDATES:\n{json.dumps(batch, ensure_ascii=False, default=str)[:62000]}

Return exactly:
{{"assessments":[{{
  "key":"candidate key exactly as supplied",
  "relevance_score":0.0,
  "rationale":"why it is worth screening, phrased as metadata/abstract-level relevance",
  "target_gaps":["..."],
  "target_hypotheses":[{{"hypothesis":"...","relation":"supports_if_confirmed|refutes_if_confirmed|discriminates|not_applicable"}}],
  "expected_contribution":"what a full-text review could contribute",
  "risks":["abstract-only", "method mismatch", "different regime", "secondary source", "other"],
  "recommendation":"include|review|exclude"
}}]}}"""
        try:
            raw = self.provider.complete(system, user)  # type: ignore[attr-defined]
            parsed = _parse_json_response(raw)
        except Exception:
            return {}
        allowed = {row["canonical_key"] for row in candidates}
        output: dict[str, dict[str, Any]] = {}
        for item in parsed.get("assessments") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            if key not in allowed:
                continue
            try:
                ai_score = max(0.0, min(1.0, float(item.get("relevance_score") or 0)))
            except (TypeError, ValueError):
                ai_score = 0.0
            recommendation = str(item.get("recommendation") or "review").lower()
            if recommendation not in _ALLOWED_RECOMMENDATIONS:
                recommendation = "review"
            output[key] = {
                "ai_score": ai_score,
                "rationale": str(item.get("rationale") or "").strip(),
                "target_gaps": [str(x).strip() for x in item.get("target_gaps") or [] if str(x).strip()][:8],
                "target_hypotheses": [x for x in item.get("target_hypotheses") or [] if isinstance(x, dict)][:8],
                "expected_contribution": str(item.get("expected_contribution") or "").strip(),
                "risks": [str(x).strip() for x in item.get("risks") or [] if str(x).strip()][:8],
                "recommendation": recommendation,
            }
        return output

    def _candidate_payload(self, run_id: str, row: dict[str, Any], assessment: dict[str, Any] | None) -> dict[str, Any]:
        origins = row.get("query_origins") or []
        assessment = assessment or {}
        final_score = float(row.get("preliminary_score") or 0)
        if assessment:
            final_score = 0.6 * final_score + 0.4 * float(assessment.get("ai_score") or 0)
        origin_gaps = [str(x.get("target_gap") or "").strip() for x in origins if str(x.get("target_gap") or "").strip()]
        origin_hypotheses = [str(x.get("target_hypothesis") or "").strip() for x in origins if str(x.get("target_hypothesis") or "").strip()]
        rationale = assessment.get("rationale") or (
            "Candidate matched one or more autonomous search queries. Relevance is provisional until the full text is reviewed."
        )
        risks = assessment.get("risks") or ["metadata/abstract-only screening"]
        return {
            "run_id": run_id,
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "canonical_key": row["canonical_key"],
            "canonical_id": row.get("canonical_id"),
            "title": str(row.get("title") or "Untitled")[:1000],
            "authors": row.get("authors") or [],
            "publication_date": str(row.get("publication_date") or "") or None,
            "journal": row.get("journal"),
            "doi": row.get("doi"),
            "arxiv_id": row.get("arxiv_id"),
            "source": row.get("source") or "web",
            "source_url": row.get("url") or row.get("public_url"),
            "pdf_url": row.get("pdf_url"),
            "abstract": re.sub(r"<[^>]+>", " ", str(row.get("abstract") or ""))[:12000],
            "access_status": row.get("access_status") or "metadata_only",
            "access_kind": row.get("access_kind") or "unknown",
            "access_label": row.get("access_label") or "Acceso no verificado",
            "system_can_read": bool(row.get("system_can_read")),
            "cited_by_count": int(row.get("cited_by_count") or 0),
            "query_origins": origins,
            "target_gaps": list(dict.fromkeys([*(assessment.get("target_gaps") or []), *origin_gaps]))[:12],
            "target_hypotheses": (assessment.get("target_hypotheses") or []) or [
                {"hypothesis": item, "relation": "discriminates"} for item in origin_hypotheses[:8]
            ],
            "preliminary_score": float(row.get("preliminary_score") or 0),
            "relevance_score": round(max(0.0, min(1.0, final_score)), 4),
            "screening_reason": rationale,
            "expected_contribution": assessment.get("expected_contribution") or "Requires full-text review before scientific use.",
            "risks": risks,
            "recommendation": assessment.get("recommendation") or "review",
            "metadata": {
                "result_type": row.get("result_type"),
                "oa_status": row.get("oa_status"),
                "license": row.get("license"),
                "manual_lookup_required": bool(row.get("manual_lookup_required")),
                "manual_lookup_message": row.get("manual_lookup_message"),
            },
        }

    def _save_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self.workspace._select(
            "scibrain_screening_candidates",
            {
                "folder_id": f"eq.{self.folder_id}",
                "canonical_key": f"eq.{payload['canonical_key']}",
                "select": "*",
                "limit": "1",
            },
        )
        if rows:
            current = rows[0]
            preserved = {
                "decision": current.get("decision") or "pending",
                "decision_reason": current.get("decision_reason"),
                "added_item_id": current.get("added_item_id"),
            }
            updated = self.workspace._patch(
                "scibrain_screening_candidates",
                {"candidate_id": f"eq.{current['candidate_id']}"},
                {**payload, **preserved},
            )
            return {**current, **payload, **preserved, **(updated or {})}
        return self.workspace._insert(
            "scibrain_screening_candidates",
            {"candidate_id": str(uuid.uuid4()), "decision": "pending", **payload},
        )

    def run(
        self,
        *,
        focus: str = "",
        from_year: int = 1900,
        max_queries: int = 4,
        per_query: int = 12,
        language: str = "es",
    ) -> dict[str, Any]:
        context = self._context(focus)
        plan = self._plan(context, max_queries=max_queries, language=language)
        run = self._new_run(context, focus, plan, from_year)
        run_id = str(run["run_id"])
        try:
            candidates, source_summary, errors = self._collect_candidates(
                plan,
                context,
                from_year=max(1900, min(int(from_year), datetime.now(timezone.utc).year)),
                per_query=max(5, min(int(per_query), 25)),
            )
            candidates = candidates[:45]
            assessments = self._annotate(candidates, context, language=language)
            stored = [
                self._save_candidate(self._candidate_payload(run_id, row, assessments.get(row["canonical_key"])))
                for row in candidates
            ]
            stored.sort(key=lambda row: (-float(row.get("relevance_score") or 0), -int(row.get("cited_by_count") or 0)))
            status = "partial" if errors else "completed"
            self._update_run(run_id, {
                "status": status,
                "source_summary": source_summary,
                "candidate_count": len(stored),
                "errors": errors,
            })
            return {
                "run_id": run_id,
                "folder_id": self.folder_id,
                "status": status,
                "context_summary": {
                    "topic": context.get("topic"),
                    "evidence_gap_count": len(context.get("evidence_gaps") or []),
                    "contradiction_count": len(context.get("contradictions") or []),
                    "hypothesis_count": len(context.get("hypotheses") or []),
                },
                "plan": plan,
                "source_summary": source_summary,
                "errors": errors,
                "candidates": stored,
                "epistemic_note": "Discovery candidates are not evidence until added to the corpus and full-text reviewed.",
            }
        except Exception as exc:
            self._update_run(run_id, {"status": "failed", "errors": [{"source": "discovery", "error": f"{type(exc).__name__}: {exc}"}]})
            raise

    def list_candidates(self, *, decision: str | None = None, limit: int = 200) -> dict[str, Any]:
        params = {
            "folder_id": f"eq.{self.folder_id}",
            "select": "*",
            "order": "relevance_score.desc,updated_at.desc",
            "limit": str(max(1, min(limit, 500))),
        }
        if decision:
            if decision not in _ALLOWED_DECISIONS:
                raise ValueError("invalid decision")
            params["decision"] = f"eq.{decision}"
        candidates = self.workspace._select("scibrain_screening_candidates", params)
        runs = self.workspace._select(
            "scibrain_discovery_runs",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "run_id,focus,from_year,status,plan,queries,criteria,source_summary,candidate_count,errors,created_at,updated_at",
                "order": "created_at.desc",
                "limit": "10",
            },
        )
        counts = {key: 0 for key in _ALLOWED_DECISIONS}
        for row in self.workspace._select(
            "scibrain_screening_candidates",
            {"folder_id": f"eq.{self.folder_id}", "select": "decision", "limit": "5000"},
        ):
            key = str(row.get("decision") or "pending")
            counts[key] = counts.get(key, 0) + 1
        return {"folder_id": self.folder_id, "candidates": candidates, "runs": runs, "counts": counts}

    def set_decision(self, candidate_id: str, decision: str, reason: str = "") -> dict[str, Any]:
        decision = decision.strip().lower()
        if decision not in _ALLOWED_DECISIONS:
            raise ValueError("invalid decision")
        rows = self.workspace._select(
            "scibrain_screening_candidates",
            {"candidate_id": f"eq.{candidate_id}", "folder_id": f"eq.{self.folder_id}", "select": "*", "limit": "1"},
        )
        if not rows:
            raise KeyError("candidate_not_found")
        self.workspace._patch(
            "scibrain_screening_candidates",
            {"candidate_id": f"eq.{candidate_id}"},
            {"decision": decision, "decision_reason": reason.strip() or None},
        )
        return {**rows[0], "decision": decision, "decision_reason": reason.strip() or None}

    def add_candidate(self, candidate_id: str) -> dict[str, Any]:
        rows = self.workspace._select(
            "scibrain_screening_candidates",
            {"candidate_id": f"eq.{candidate_id}", "folder_id": f"eq.{self.folder_id}", "select": "*", "limit": "1"},
        )
        if not rows:
            raise KeyError("candidate_not_found")
        candidate = rows[0]
        meta = candidate.get("metadata") or {}
        paper = self.workspace.add_paper(self.folder_id, {
            "canonical_id": candidate.get("canonical_id") or candidate.get("canonical_key"),
            "title": candidate.get("title"),
            "authors": candidate.get("authors") or [],
            "publication_date": candidate.get("publication_date"),
            "journal": candidate.get("journal"),
            "doi": candidate.get("doi"),
            "arxiv_id": candidate.get("arxiv_id"),
            "source_type": candidate.get("source") or "web",
            "source_url": candidate.get("source_url"),
            "pdf_url": candidate.get("pdf_url"),
            "access_status": candidate.get("access_status") or "metadata_only",
            "access_kind": candidate.get("access_kind") or "unknown",
            "access_label": candidate.get("access_label") or "Acceso no verificado",
            "system_can_read": bool(candidate.get("system_can_read")),
            "manual_lookup_required": bool(meta.get("manual_lookup_required", not candidate.get("system_can_read"))),
            "abstract": candidate.get("abstract") or "",
            "cited_by_count": int(candidate.get("cited_by_count") or 0),
            "oa_status": meta.get("oa_status"),
            "access_license": meta.get("license"),
            "notes": "Added from ScientificBrain autonomous discovery screening. Candidate metadata is not evidence until full-text review.",
        })
        job = None
        if bool(candidate.get("system_can_read")) and paper.get("review_depth") != "full_text_reviewed":
            store = UserSnapshotStore(self.user, folder_id=self.folder_id)
            existing_jobs = store.list_jobs(folder_id=self.folder_id, limit=500)
            old = next((
                item for item in existing_jobs
                if item.get("job_type") == "review_paper"
                and (item.get("payload") or {}).get("paper_id") == paper.get("canonical_id")
                and item.get("status") in {"pending", "running", "completed"}
            ), None)
            job = old or store.create_job(
                None,
                "review_paper",
                {"paper_id": paper.get("canonical_id"), "pdf_url": paper.get("pdf_url") or candidate.get("pdf_url")},
                folder_id=self.folder_id,
            )
        self.workspace._patch(
            "scibrain_screening_candidates",
            {"candidate_id": f"eq.{candidate_id}"},
            {"decision": "included", "decision_reason": "Added to corpus", "added_item_id": paper.get("item_id")},
        )
        return {"candidate_id": candidate_id, "paper": paper, "review_job": job}
