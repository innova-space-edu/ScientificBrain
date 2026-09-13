from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from urllib.parse import quote_plus

import httpx

from .models import Paper
from .taxonomy import classify_topics


def _invert_abstract(index: dict | None) -> str:
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in index.items():
        positions.extend((i, word) for i in indexes)
    return " ".join(word for _, word in sorted(positions))


def _canonical(doi: str | None, arxiv_id: str | None, openalex_id: str | None) -> str:
    if doi:
        return "doi:" + doi.lower().removeprefix("https://doi.org/")
    if arxiv_id:
        return "arxiv:" + arxiv_id
    if openalex_id:
        return "openalex:" + openalex_id.rsplit("/", 1)[-1]
    raise ValueError("Paper needs at least one stable identifier")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(x.strip() for x in values if x and x.strip()))


class OpenAlexClient:
    BASE = "https://api.openalex.org/works"

    def __init__(self, taxonomy: dict, mailto: str | None = None) -> None:
        self.taxonomy = taxonomy
        self.mailto = mailto

    def search(self, query: str, from_year: int = 1900, per_page: int = 100) -> list[Paper]:
        params = {
            "search": query,
            "filter": f"from_publication_date:{from_year}-01-01",
            "per-page": min(per_page, 200),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        data = httpx.get(self.BASE, params=params, timeout=30).raise_for_status().json()
        papers: list[Paper] = []
        for work in data.get("results", []):
            doi = work.get("doi")
            title = work.get("title") or "Untitled"
            abstract = _invert_abstract(work.get("abstract_inverted_index"))
            openalex_topics = [
                str(topic.get("display_name") or "")
                for topic in (work.get("topics") or [])
                if isinstance(topic, dict)
            ]
            taxonomy_topics = classify_topics(f"{title}\n{abstract}", self.taxonomy)
            topics = _unique(openalex_topics + taxonomy_topics)
            pub_date = None
            if work.get("publication_date"):
                try:
                    pub_date = date.fromisoformat(work["publication_date"])
                except ValueError:
                    pass
            papers.append(Paper(
                canonical_id=_canonical(doi, None, work.get("id")),
                title=title,
                abstract=abstract,
                authors=[
                    a.get("author", {}).get("display_name", "")
                    for a in work.get("authorships", []) if a.get("author")
                ],
                publication_date=pub_date,
                journal=((work.get("primary_location") or {}).get("source") or {}).get("display_name"),
                doi=doi.removeprefix("https://doi.org/") if doi else None,
                openalex_id=work.get("id"),
                url=(work.get("primary_location") or {}).get("landing_page_url") or doi,
                cited_by_count=work.get("cited_by_count", 0),
                # Legacy field name retained for backward compatibility; it now carries
                # general scientific topic labels as well as optional plasma taxonomy labels.
                plasma_topics=topics,
                source="openalex",
            ))
        return papers


class ArxivClient:
    BASE = "https://export.arxiv.org/api/query"
    NS = {"a": "http://www.w3.org/2005/Atom"}

    def __init__(self, taxonomy: dict) -> None:
        self.taxonomy = taxonomy

    def search(self, query: str, max_results: int = 100) -> list[Paper]:
        url = f"{self.BASE}?search_query=all:{quote_plus(query)}&start=0&max_results={min(max_results, 200)}&sortBy=submittedDate&sortOrder=descending"
        xml = httpx.get(url, timeout=30).raise_for_status().text
        root = ET.fromstring(xml)
        papers: list[Paper] = []
        for entry in root.findall("a:entry", self.NS):
            arxiv_url = entry.findtext("a:id", default="", namespaces=self.NS)
            arxiv_id = arxiv_url.rsplit("/", 1)[-1]
            title = re.sub(r"\s+", " ", entry.findtext("a:title", default="", namespaces=self.NS)).strip()
            abstract = re.sub(r"\s+", " ", entry.findtext("a:summary", default="", namespaces=self.NS)).strip()
            published = entry.findtext("a:published", default="", namespaces=self.NS)
            pub_date = date.fromisoformat(published[:10]) if published else None
            authors = [x.findtext("a:name", default="", namespaces=self.NS) for x in entry.findall("a:author", self.NS)]
            categories = [x.attrib.get("term", "") for x in entry.findall("a:category", self.NS)]
            doi = None
            for link in entry.findall("a:link", self.NS):
                href = link.attrib.get("href", "")
                if "doi.org/" in href:
                    doi = href.split("doi.org/", 1)[1]
            topics = _unique(categories + classify_topics(f"{title}\n{abstract}", self.taxonomy))
            papers.append(Paper(
                canonical_id=_canonical(doi, arxiv_id, None),
                title=title,
                abstract=abstract,
                authors=authors,
                publication_date=pub_date,
                doi=doi,
                arxiv_id=arxiv_id,
                url=arxiv_url,
                plasma_topics=topics,
                source="arxiv",
            ))
        return papers
