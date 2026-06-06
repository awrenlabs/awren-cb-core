"""Awren Core CLI — Command-line interface for the Cognitive OS.

Usage:
    awren --help
    awren entity create Organization "Acme Corp"
    awren entity list
    awren entity get <uuid>
    awren entity update <uuid> --label "New Name"
    awren entity delete <uuid>
    awren event list
    awren event list --entity-id <uuid>
    awren query "find all organizations"
    awren health
"""

import asyncio
import json
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from awren_sdk.client import AwrenClient

app = typer.Typer(
    name="awren",
    help="Awren Core CLI — Cognitive Operating System",
    no_args_is_help=True,
)
entity_app = typer.Typer(help="Manage knowledge graph entities")
event_app = typer.Typer(help="Query the event log")
agent_app = typer.Typer(help="Run AI agents against the knowledge graph")
app.add_typer(entity_app, name="entity")
app.add_typer(event_app, name="event")
app.add_typer(agent_app, name="agent")

console = Console()
_DEFAULT_BASE_URL = "http://localhost:8000"


def _get_client(base_url: Optional[str] = None) -> AwrenClient:
    """Create an AwrenClient connected to the given or default API URL."""
    return AwrenClient(base_url or _DEFAULT_BASE_URL)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a sync context."""
    return asyncio.run(coro)


def _print_entity(entity: dict[str, Any]) -> None:
    """Print a single entity to the console."""
    table = Table(title=f"Entity: {entity.get('label', '')}", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("ID", entity.get("id", ""))
    table.add_row("Type", entity.get("type", ""))
    table.add_row("Label", entity.get("label", ""))
    table.add_row("Description", entity.get("description", "") or "")
    table.add_row("Properties", json.dumps(entity.get("properties", {}), indent=2))
    table.add_row("Identifiers", json.dumps(entity.get("identifiers", []), indent=2))
    console.print(table)


def _print_entities(entities: list[dict[str, Any]], total: int) -> None:
    """Print a list of entities as a table."""
    table = Table(title=f"Entities ({total} total)")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Label", style="white")
    table.add_column("Description", style="green")
    for entity in entities[:50]:  # Show at most 50 rows
        table.add_row(
            entity.get("id", "")[:8] + "...",
            entity.get("type", ""),
            entity.get("label", ""),
            (entity.get("description") or "")[:60],
        )
    if len(entities) > 50:
        console.print(f"Showing 50 of {total} entities. Use --limit to show more.")
    console.print(table)


def _print_events(events: list[dict[str, Any]], total: int) -> None:
    """Print a list of events as a table."""
    table = Table(title=f"Events ({total} total)")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Subject", style="white")
    table.add_column("Timestamp", style="green")
    for event in events:
        table.add_row(
            event.get("id", "")[:8] + "...",
            event.get("type", ""),
            str(event.get("subject_id", ""))[:8] + "...",
            str(event.get("timestamp", ""))[:19],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.command()
def health(
    base_url: Optional[str] = typer.Option(
        None, "--url", "-u", help="API base URL",
    ),
) -> None:
    """Check API health status."""
    client = _get_client(base_url)
    try:
        result = _run_async(client.health_check())
        console.print(f"[green]Status:[/green] {result.get('status', 'unknown')}")
        console.print(f"[green]Version:[/green] {result.get('version', 'unknown')}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Entity commands
# ---------------------------------------------------------------------------


@entity_app.command("create")
def entity_create(
    entity_type: str = typer.Argument(..., help="Entity type (e.g. core:Organization)"),
    label: str = typer.Argument(..., help="Entity label/name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Optional description"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """Create a new entity in the knowledge graph."""
    client = _get_client(base_url)
    try:
        kwargs: dict[str, Any] = {}
        if description:
            kwargs["description"] = description
        result = _run_async(client.create_entity(entity_type, label, **kwargs))
        _print_entity(result)
        console.print("[green]Entity created successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@entity_app.command("get")
def entity_get(
    entity_id: str = typer.Argument(..., help="Entity UUID"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """Get a single entity by ID."""
    client = _get_client(base_url)
    try:
        result = _run_async(client.get_entity(entity_id))
        _print_entity(result)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@entity_app.command("list")
def entity_list(
    entity_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by entity type",
    ),
    limit: int = typer.Option(100, "--limit", "-l", help="Max results"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """List entities, optionally filtered by type."""
    client = _get_client(base_url)
    try:
        result = _run_async(client.list_entities(entity_type=entity_type, limit=limit))
        entities = result.get("entities", [])
        total = result.get("total", len(entities))
        if not entities:
            console.print("No entities found.")
            return
        _print_entities(entities, total)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@entity_app.command("update")
def entity_update(
    entity_id: str = typer.Argument(..., help="Entity UUID"),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="New label"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """Update an entity's label and/or description."""
    client = _get_client(base_url)
    try:
        patch_data: dict[str, Any] = {}
        if label is not None:
            patch_data["label"] = label
        if description is not None:
            patch_data["description"] = description
        if not patch_data:
            console.print("[yellow]No fields to update. Provide --label and/or --description.[/yellow]")
            return
        result = _run_async(client.update_entity(entity_id, patch_data))
        _print_entity(result)
        console.print("[green]Entity updated successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@entity_app.command("delete")
def entity_delete(
    entity_id: str = typer.Argument(..., help="Entity UUID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """Delete an entity by ID (requires confirmation)."""
    if not yes:
        typer.confirm(f"Are you sure you want to delete entity {entity_id}?", abort=True)
    client = _get_client(base_url)
    try:
        _run_async(client.delete_entity(entity_id))
        console.print(f"[green]Entity {entity_id} deleted.[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Event commands
# ---------------------------------------------------------------------------


@event_app.command("list")
def event_list(
    entity_id: Optional[str] = typer.Option(
        None, "--entity-id", "-e", help="Filter by entity UUID",
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max events"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """List events, optionally filtered by entity."""
    client = _get_client(base_url)
    try:
        if entity_id:
            data = _run_async(client.get_entity_events(entity_id))
        else:
            data = _run_async(client.get_recent_events(limit=limit))
        events = data.get("events", [])
        total = data.get("total", len(events))
        if not events:
            console.print("No events found.")
            return
        _print_events(events, total)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@event_app.command("replay")
def event_replay(
    entity_id: str = typer.Argument(..., help="Entity UUID to replay events for"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """Replay all events for an entity in chronological order."""
    client = _get_client(base_url)
    try:
        data = _run_async(client.replay_entity_events(entity_id))
        events = data.get("events", [])
        total = data.get("total", len(events))
        if not events:
            console.print(f"No events found for entity {entity_id}.")
            return
        console.print(f"[cyan]Event History for {entity_id}:[/cyan]")
        for i, event in enumerate(events, 1):
            console.print(f"  {i}. [{event.get('type', '')}] at {str(event.get('timestamp', ''))[:19]}")
            if event.get("payload"):
                console.print(f"     Payload: {json.dumps(event['payload'], default=str)}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Agent commands
# ---------------------------------------------------------------------------


@agent_app.command("research")
def agent_research(
    query_text: str = typer.Argument(..., help="Research query"),
    entity_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by entity type",
    ),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """Run the Research Agent against the knowledge graph.

    Searches entities, applies deductive rules, and uses LLM
    reasoning to produce structured answers.
    """
    client = _get_client(base_url)
    try:
        result = _run_async(client.agent_research(query_text, entity_type=entity_type))
        output = result.get("output", {})
        confidence = result.get("confidence", 0.0)
        exec_time = result.get("execution_time_ms", 0.0)

        console.print(f"[bold cyan]Research Result[/bold cyan]")
        console.print(f"[dim]Confidence: {confidence:.1%} | Time: {exec_time}ms[/dim]")
        console.print()

        # Show entities found
        entities = output.get("entities", [])
        if entities:
            console.print(f"[green]{len(entities)} entities found[/green]")
            for e in entities[:10]:
                console.print(f"  • [{e.get('type', '')}] {e.get('label', '')}")
            console.print()

        # Show deductive conclusions
        conclusions = output.get("deductive_conclusions", [])
        if conclusions:
            console.print("[yellow]Deductive Conclusions:[/yellow]")
            for c in conclusions:
                conf = c.get("confidence", 0.0)
                label = f"[green]✓[/green]" if conf > 0.5 else "[dim]—[/dim]"
                console.print(f"  {label} {c.get('conclusion', '')} ({conf:.0%})")
            console.print()

        # Show inductive patterns
        patterns = output.get("inductive_patterns", [])
        if patterns:
            console.print("[cyan]Patterns Found:[/cyan]")
            for p in patterns[:5]:
                console.print(f"  • {p.get('pattern', '')}")
            console.print()

        # Show abductive explanations
        explanations = output.get("abductive_explanations", [])
        if explanations:
            console.print("[magenta]Explanations:[/magenta]")
            for e in explanations[:5]:
                console.print(f"  • {e.get('hypothesis', '')} ({e.get('plausibility', 0.0):.0%})")
            console.print()

        if not entities and not conclusions and not patterns:
            console.print("[yellow]No findings. Try a broader query.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@app.command()
def query(
    query_text: str = typer.Argument(..., help="Query text"),
    limit: int = typer.Option(100, "--limit", "-l", help="Max results"),
    base_url: Optional[str] = typer.Option(None, "--url", "-u", help="API base URL"),
) -> None:
    """Query the knowledge graph."""
    client = _get_client(base_url)
    try:
        result = _run_async(client.query(query_text, limit=limit))
        results = result.get("results", [])
        total = result.get("total", len(results))
        query_time = result.get("query_time_ms", 0)
        if not results:
            console.print(f"[yellow]No results for query:[/yellow] {query_text}")
            return
        console.print(f"[green]Query completed in {query_time}ms:[/green] {total} result(s)")
        for i, r in enumerate(results, 1):
            console.print(f"  {i}. [{r.get('type', '')}] {r.get('label', '')} — {r.get('id', '')}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def cli() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli()
