"""Brompt CLI — Typer-based command-line interface with Rich formatting."""

import difflib
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from brompt.core.engine import BromptEngine
from brompt.core.template_engine import template_registry
from brompt.hooks import LoggingHook, TimingHook, hooks_manager
from brompt.observability import metrics
from brompt.providers_core import build_provider_from_env
from brompt.receipt import Receipt, load_receipt, save_receipt, verify_receipt

app = typer.Typer(
    name="brompt",
    help="Brompt Engine — Deterministic State-Driven LLM Orchestration",
    add_completion=False,
)
console = Console()


def _version_callback(value: bool):
    if value:
        from brompt import __version__
        console.print(f"Brompt Engine [bold]v{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.", callback=_version_callback),
):
    pass


@app.command()
def chat(
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider override."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override."),
):
    """Start an interactive chat session."""
    engine = _load_engine(config)
    hooks_manager.register(LoggingHook())
    hooks_manager.register(TimingHook())

    help_text = "[bold cyan]Brompt Chat Session[/bold cyan]\n"
    help_text += "Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit."
    console.print(Panel(help_text))

    while True:
        try:
            user_input = console.input("\n[bold yellow]╰─>[/bold yellow] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Exiting chat...[/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            _handle_chat_command(engine, user_input)
            continue

        try:
            query, context = hooks_manager.before_execute(user_input, None)
            result = engine.execute(query, context)
            result = hooks_manager.after_execute(result)

            if result.is_secure:
                response = result.data.get("llm_response", "")
                if response:
                    console.print(f"[bold green]├──>[/bold green] {response}")
                else:
                    console.print("[dim]├──> No response (dry-run mode)[/dim]")
            else:
                console.print(f"[bold red]├──> Error:[/bold red] {result.error_message}")
        except Exception as exc:
            console.print(f"[bold red]├──> Error:[/bold red] {exc}")


@app.command()
def run(
    prompt: str = typer.Argument(..., help="The prompt to execute."),
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
    context: Optional[str] = typer.Option(None, "--context", help="JSON context string."),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Template name to use."),
):
    """Execute a single prompt and print the result."""
    engine = _load_engine(config)
    ctx = json.loads(context) if context else None

    if template:
        try:
            prompt = template_registry.render(template, user_message=prompt, **(ctx or {}))
        except Exception as exc:
            console.print(f"[red]Template error: {exc}[/red]")
            raise typer.Exit(1)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as p:
        p.add_task("[yellow]Executing...", total=None)
        result = engine.execute(prompt, ctx)

    if result.is_secure:
        response = result.data.get("llm_response", "")
        if response:
            console.print(Panel(response, title="[bold green]Response[/bold green]", border_style="green"))
        else:
            console.print("[dim]No response (dry-run mode)[/dim]")
    else:
        console.print(f"[red]Error: {result.error_message}[/red]")
        raise typer.Exit(1)


@app.command()
def history(
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of entries to show."),
):
    """Show conversation history."""
    engine = _load_engine(config)
    entries = engine.memory.get_history()[-limit:]
    if not entries:
        console.print("[dim]No history available.[/dim]")
        return
    table = Table(title="Conversation History", border_style="cyan")
    table.add_column("#", width=4)
    table.add_column("Role", width=12)
    table.add_column("Content")
    for i, entry in enumerate(entries, 1):
        content = entry["content"][:120] + "..." if len(entry["content"]) > 120 else entry["content"]
        table.add_row(str(i), entry["role"], content)
    console.print(table)


@app.command()
def audit(
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of entries to show."),
):
    """Show audit log entries."""
    engine = _load_engine(config)
    entries = engine.audit.read_all()[-limit:]
    if not entries:
        console.print("[dim]No audit entries.[/dim]")
        return
    table = Table(title="Audit Log", border_style="yellow")
    table.add_column("#", width=4)
    table.add_column("Event", width=18)
    table.add_column("State ID", width=18)
    table.add_column("Secure", width=8)
    for i, entry in enumerate(entries, 1):
        secure = "[green]Yes[/green]" if entry.get("is_secure") else "[red]No[/red]"
        table.add_row(str(i), entry["event"], entry["state_id"][:16], secure)
    console.print(table)
    valid = engine.audit.verify()
    color = "green" if valid else "red"
    console.print(f"[{color}]Chain integrity: {'VALID' if valid else 'TAMPERED'}[/{color}]")


@app.command()
def replay(
    audit_id: str = typer.Argument(..., help="Audit entry hash or execution id to re-run."),
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Provider model override for the re-run."),
    no_diff: bool = typer.Option(False, "--no-diff", help="Print the replayed output without a diff."),
):
    """Deterministically re-run a recorded execution and diff the output."""
    engine = _load_engine(config, allow_missing=True)
    entry_hash = _resolve_audit_id(engine, audit_id)
    if entry_hash is None:
        console.print(f"[red]Audit entry not found: {audit_id}[/red]")
        raise typer.Exit(2)
    provider = build_provider_from_env(model=model) if model else engine.provider
    result = engine.replay(entry_hash, provider)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        raise typer.Exit(2)
    original = result["original"]
    replayed = result["replayed"]
    original_text = original.get("response") or ""
    if not original_text:
        original_text = "".join(
            m.get("content", "") for m in (original.get("messages") or [])
        )
    new_text = getattr(replayed, "text", "")
    replayed_model = getattr(replayed, "model", "replay")
    console.print(f"[bold]Replay of {entry_hash}[/bold] (original -> {replayed_model})")
    if no_diff:
        console.print(new_text)
        return
    diff = list(difflib.unified_diff(
        original_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="original",
        tofile=f"replayed ({replayed_model})",
        lineterm="",
    ))
    if not diff:
        console.print("[green]Outputs are identical.[/green]")
        return
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            color = "green"
        elif line.startswith("-") and not line.startswith("---"):
            color = "red"
        elif line.startswith("@"):
            color = "cyan"
        else:
            color = "dim"
        console.print(f"[{color}]{line.rstrip()}[/{color}]")
    raise typer.Exit(1)


@app.command()
def receipt(
    audit_id: Optional[str] = typer.Argument(None, help="Audit entry hash or execution id to attest."),
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output .receipt file path."),
    verify: bool = typer.Option(False, "--verify", help="Verify a .receipt file instead of creating one."),
):
    """Export or verify a standalone signed execution receipt."""
    if verify:
        if not output:
            console.print("[red]--verify requires --output <file>.[/red]")
            raise typer.Exit(2)
        engine = _load_engine(config, allow_missing=True)
        report = verify_receipt(load_receipt(output), engine.audit)
        color = "green" if report["ok"] else "red"
        console.print(
            f"[{color}]Receipt {'VALID' if report['ok'] else 'INVALID'}: "
            f"{report['reason']}[/{color}]"
        )
        raise typer.Exit(0 if report["ok"] else 1)
    if not audit_id:
        console.print("[red]An audit id (entry hash or execution id) is required.[/red]")
        raise typer.Exit(2)
    engine = _load_engine(config, allow_missing=True)
    entry_hash = _resolve_audit_id(engine, audit_id)
    if entry_hash is None:
        console.print(f"[red]Audit entry not found: {audit_id}[/red]")
        raise typer.Exit(2)
    entry = engine.audit.find_entry(entry_hash)
    built = Receipt.from_audit_entry(entry, engine.audit)
    out = output or f"{entry_hash}.receipt"
    save_receipt(built, out)
    console.print(f"[green]Wrote {out} (audit_hash={entry_hash})[/green]")


@app.command()
def status(
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
):
    """Show engine status and configuration."""
    engine = _load_engine(config)
    provider_name = type(engine.provider).__name__ if engine.provider else "None (dry-run)"
    table = Table(title="Engine Status", border_style="cyan")
    table.add_column("Field", width=22)
    table.add_column("Value")
    table.add_row("Provider", provider_name)
    table.add_row("Provider Enabled", str(engine.provider is not None))
    table.add_row("State ID", engine.state_id)
    table.add_row("History Size", str(len(engine.memory.get_history())))
    table.add_row("Max History", str(engine.memory.max_turns))
    table.add_row("Audit Entries", str(len(engine.audit.read_all())))
    table.add_row("Audit Valid", str(engine.audit.verify()))
    metrics_snapshot = metrics.snapshot()
    table.add_row("Metrics Counters", str(len(metrics_snapshot["counters"])))
    table.add_row("Hooks Active", str(hooks_manager.list_hooks()))
    console.print(table)


@app.command()
def templates(
    name: Optional[str] = typer.Argument(None, help="Template name to render (omit to list)."),
    vars: Optional[str] = typer.Option(None, "--vars", "-v", help="JSON variables for template rendering."),
):
    """List or render prompt templates."""
    if name:
        tpl = template_registry.get(name)
        if tpl is None:
            console.print(f"[red]Template '{name}' not found.[/red]")
            raise typer.Exit(1)
        variables = json.loads(vars) if vars else {}
        try:
            rendered = tpl.render(**variables)
            console.print(Panel(rendered, title=f"[bold]Template: {name}[/bold]", border_style="blue"))
        except Exception as exc:
            console.print(f"[red]Render error: {exc}[/red]")
    else:
        names = template_registry.list()
        if not names:
            console.print("[dim]No templates registered.[/dim]")
            return
        table = Table(title="Available Templates", border_style="blue")
        table.add_column("Name", width=20)
        table.add_column("Source Preview")
        for n in names:
            tpl = template_registry.get(n)
            preview = tpl.source[:80] + "..." if tpl and len(tpl.source) > 80 else (tpl.source if tpl else "")
            table.add_row(n, preview)
        console.print(table)


@app.command()
def config(
    path: str = typer.Argument("agent.brompt.yaml", help="Path to config file."),
    show: bool = typer.Option(False, "--show", "-s", help="Show raw config contents."),
):
    """Show or validate a Brompt config file."""
    cfg_path = Path(path)
    if not cfg_path.exists():
        console.print(f"[red]Config file not found: {path}[/red]")
        raise typer.Exit(1)
    import yaml
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if show:
        syntax = Syntax(json.dumps(data, indent=2, ensure_ascii=False), "json", theme="monokai")
        console.print(Panel(syntax, title=f"[bold]{path}[/bold]", border_style="green"))
    else:
        name = data.get("metadata", {}).get("name", "unknown")
        version = data.get("metadata", {}).get("version", "?")
        console.print(f"[bold]Name:[/bold] {name}  [bold]Version:[/bold] {version}")
        console.print(f"[bold]Path:[/bold] {cfg_path.resolve()}")


@app.command()
def clear(
    config: str = typer.Option("agent.brompt.yaml", "--config", "-c", help="Path to config file."),
):
    """Clear engine memory and history."""
    engine = _load_engine(config)
    engine.memory.clear()
    console.print("[green]Memory cleared.[/green]")


def _load_engine(config_path: str, allow_missing: bool = False) -> BromptEngine:
    path = _find_config(config_path)
    try:
        return BromptEngine(path, allow_missing_manifest=allow_missing)
    except FileNotFoundError as exc:
        console.print(f"[red]Config Error: {exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]Engine Error: {exc}[/red]")
        raise typer.Exit(1)


def _resolve_audit_id(engine: BromptEngine, audit_id: str) -> Optional[str]:
    """Resolve an entry hash or execution id to a canonical entry hash."""
    if engine.audit.find_entry(audit_id):
        return audit_id
    entry = engine.audit.find_by_state(audit_id)
    if entry:
        return entry.get("entry_hash")
    return None


def _find_config(config_path: str) -> str:
    path = Path(config_path)
    if path.exists():
        return str(path.resolve())
    candidates = [Path.cwd(), Path(__file__).resolve().parent.parent.parent.parent]
    for base in candidates:
        cfg = base / config_path
        if cfg.exists():
            return str(cfg.resolve())
    return config_path


def _handle_chat_command(engine: BromptEngine, cmd: str):
    cmd = cmd.lower()
    if cmd in ("/exit", "/quit"):
        console.print("[dim]Exiting chat...[/dim]")
        raise SystemExit(0)
    elif cmd == "/help":
        table = Table(title="Chat Commands", border_style="cyan")
        table.add_column("Command", width=12)
        table.add_column("Description")
        table.add_row("/help", "Show this help")
        table.add_row("/status", "Show engine status")
        table.add_row("/history", "Show history")
        table.add_row("/audit", "Show audit log")
        table.add_row("/clear", "Clear memory")
        table.add_row("/exit", "Exit chat")
        console.print(table)
    elif cmd == "/status":
        provider_name = type(engine.provider).__name__ if engine.provider else "None"
        console.print(f"Provider: {provider_name}")
        console.print(f"State ID: {engine.state_id}")
        console.print(f"History: {len(engine.memory.get_history())} turns")
    elif cmd == "/history":
        entries = engine.memory.get_history()
        for i, entry in enumerate(entries, 1):
            console.print(f"[dim]{i}.[/dim] {entry['role']}: {entry['content'][:120]}")
    elif cmd == "/audit":
        entries = engine.audit.read_all()
        for entry in entries[-10:]:
            secure = "✓" if entry.get("is_secure") else "✗"
            console.print(f"[dim]{entry['event']}[/dim] {secure} {entry['state_id'][:12]}")
    elif cmd == "/clear":
        engine.memory.clear()
        console.print("[green]Memory cleared.[/green]")
    else:
        console.print(f"[red]Unknown command: {cmd}. Type /help for commands.[/red]")


def cli_main():
    """Entry point for the `brompt` console script."""
    app()
