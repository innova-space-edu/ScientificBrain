from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from .discovery import OpenAlexClient
from .memory import ScientificMemory
from .taxonomy import load_taxonomy

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("init-db")
def init_db(db: Path = Path("scientific_brain.db")) -> None:
    memory = ScientificMemory(db)
    console.print({"database": str(db), **memory.stats()})
    memory.close()


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
    memory = ScientificMemory(db)
    total = 0
    for item in plan:
        papers = client.search(item["query"], item.get("from_year", 1900), max_results)
        for paper in papers:
            memory.upsert_paper(paper)
        total += len(papers)
        console.print(f"[bold]{item['id']}[/bold]: {len(papers)} records")
    console.print({"discovered_this_run": total, **memory.stats()})
    memory.close()


@app.command("search")
def search(query: str, db: Path = Path("scientific_brain.db"), limit: int = 20) -> None:
    memory = ScientificMemory(db)
    rows = memory.search(query, limit)
    table = Table("Year", "Title", "DOI", "Topics")
    for row in rows:
        table.add_row((row.get("publication_date") or "")[:4], row["title"], row.get("doi") or "", row["topics_json"])
    console.print(table)
    memory.close()


@app.command("stats")
def stats(db: Path = Path("scientific_brain.db")) -> None:
    memory = ScientificMemory(db)
    console.print(memory.stats())
    memory.close()


if __name__ == "__main__":
    app()
