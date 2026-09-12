from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from .corpus import audit_corpus, coverage_gaps, load_corpus_policy
from .discovery import OpenAlexClient
from .memory import ScientificMemory
from .models import ReviewDepth
from .providers import provider_from_env
from .taxonomy import load_taxonomy
from .workflow import ScientificWorkflow

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("init-db")
def init_db(db: Path = Path("scientific_brain.db")) -> None:
    with ScientificMemory(db) as memory:
        console.print({"database": str(db), **memory.stats()})


@app.command("discover")
def discover(
    db: Path = Path("scientific_brain.db"),
    searches: Path = Path("config/plasma_searches.yaml"),
    taxonomy: Path = Path("config/plasma_taxonomy.yaml"),
    query_id: str | None = None,
    max_results: int = typer.Option(100, min=1, max=200),
    mailto: str | None = None,
) -> None:
    """Discover plasma literature through OpenAlex and deduplicate it into local memory."""
    tax = load_taxonomy(taxonomy)
    plan = yaml.safe_load(searches.read_text(encoding="utf-8"))["searches"]
    if query_id:
        plan = [x for x in plan if x["id"] == query_id]
        if not plan:
            raise typer.BadParameter(f"Unknown query_id: {query_id}")
    client = OpenAlexClient(tax, mailto=mailto)
    with ScientificMemory(db) as memory:
        total = 0
        for item in plan:
            papers = client.search(item["query"], item.get("from_year", 1900), max_results)
            for paper in papers:
                memory.upsert_paper(paper)
            total += len(papers)
            console.print(f"[bold]{item['id']}[/bold]: {len(papers)} records")
        console.print({"discovered_this_run": total, **memory.stats()})


@app.command("search")
def search(query: str, db: Path = Path("scientific_brain.db"), limit: int = 20) -> None:
    with ScientificMemory(db) as memory:
        rows = memory.search(query, limit)
        table = Table("Year", "Title", "DOI", "Topics")
        for row in rows:
            table.add_row(
                (row.get("publication_date") or "")[:4],
                row["title"],
                row.get("doi") or "",
                row["topics_json"],
            )
        console.print(table)


@app.command("stats")
def stats(db: Path = Path("scientific_brain.db")) -> None:
    with ScientificMemory(db) as memory:
        console.print(memory.stats())


@app.command("corpus-audit")
def corpus_audit(
    db: Path = Path("scientific_brain.db"),
    policy: Path = Path("config/corpus_policy.yaml"),
) -> None:
    """Verify the 100-paper corpus target, deep-analysis depth and coverage requirements."""
    with ScientificMemory(db) as memory:
        config = load_corpus_policy(policy)
        audit = audit_corpus(memory, config)
        payload = audit.model_dump()
        payload["domain_gaps"] = coverage_gaps(memory, config)
        console.print_json(data=payload)


@app.command("review-paper")
def review_paper(
    paper_id: str,
    text_file: Path,
    db: Path = Path("scientific_brain.db"),
    provider: str = typer.Option("ollama", help="ollama or openai-compatible"),
    depth: str = typer.Option(ReviewDepth.FULL_TEXT.value),
) -> None:
    """Run extraction, independent specialist reviews and scientific gates for one paper."""
    if not text_file.exists():
        raise typer.BadParameter(f"Text file not found: {text_file}")
    try:
        review_depth = ReviewDepth(depth)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid review depth: {depth}") from exc

    llm = provider_from_env(provider)
    text = text_file.read_text(encoding="utf-8")
    with ScientificMemory(db) as memory:
        workflow = ScientificWorkflow(memory, llm)
        result = workflow.review_paper(
            paper_id,
            text,
            depth=review_depth,
            source_path=str(text_file),
        )
        console.print_json(data=result.model_dump(mode="json"))


@app.command("start-research")
def start_research(
    question: str,
    db: Path = Path("scientific_brain.db"),
    search_query: str | None = None,
    limit: int = typer.Option(20, min=1, max=100),
) -> None:
    """Create a persistent ResearchState using locally indexed scientific memory."""
    with ScientificMemory(db) as memory:
        workflow = ScientificWorkflow(memory, provider=object())
        state = workflow.start_session(
            question,
            search_query=search_query,
            limit=limit,
        )
        console.print_json(data=state.model_dump(mode="json"))


@app.command("synthesize")
def synthesize(
    session_id: str,
    db: Path = Path("scientific_brain.db"),
    provider: str = typer.Option("ollama", help="ollama or openai-compatible"),
) -> None:
    """Synthesize only papers that have passed evidence and provenance gates."""
    llm = provider_from_env(provider)
    with ScientificMemory(db) as memory:
        workflow = ScientificWorkflow(memory, llm)
        state = workflow.synthesize_session(session_id)
        console.print_json(data=state.model_dump(mode="json"))


if __name__ == "__main__":
    app()
