"""Terminal User Interface for interacting with Brompt Engine."""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import json
import time

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

BANNER = r"""
     ███████████                                                █████   
    ░░███░░░░░███                                              ░░███    
     ░███    ░███ ████████   ██████  █████████████   ████████  ███████  
     ░██████████ ░░███░░███ ███░░███░░███░░███░░███ ░░███░░███░░░███░   
     ░███░░░░░███ ░███ ░░░ ░███ ░███ ░███ ░███ ░███  ░███ ░███  ░███    
     ░███    ░███ ░███     ░███ ░███ ░███ ░███ ░███  ░███ ░███  ░███ ███
     ███████████  █████    ░░██████  █████░███ █████ ░███████   ░░█████ 
    ░░░░░░░░░░░  ░░░░░      ░░░░░░  ░░░░░ ░░░ ░░░░░  ░███░░░     ░░░░░  
                                                 ░███               
                                                 █████              
                                                ░░░░░               
"""

console = Console()

BOOT_STEPS = [
    ("Building AST Compiler", 0.6),
    ("Setting up Virtual Memory", 0.5),
    ("Injecting Guardrails", 0.7),
    ("Hydrating Schema Contracts", 0.4),
    ("Initializing State Engine", 0.3),
]


def boot_animation():
    """Startup sequence: banner + progress bar."""
    console.print()
    console.print(Text(BANNER, style="bold cyan"))
    console.print(
        Panel.fit(
            "[bold white]Zero-Trust AI Middleware Runtime[/bold white]\n"
            "[dim]Classification: Zero-Trust AI Execution Runtime & State Engine[/dim]\n"
            "[dim]Target Release: v0.1.0-alpha[/dim]\n"
            "[dim]Author: SH ÂZZOUZ[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("[yellow]Initializing...[/yellow]", total=len(BOOT_STEPS))
        for label, delay in BOOT_STEPS:
            progress.update(task, description=f"[yellow]{label}[/yellow]")
            time.sleep(delay)
            progress.advance(task)

    console.print("[bold green]✔ All subsystems loaded.[/bold green]\n")


def print_help():
    """Display available commands."""
    table = Table(
        title="Brompt CLI Commands",
        border_style="cyan",
        title_style="bold cyan",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Command", style="bold yellow", width=18)
    table.add_column("Description")
    table.add_row("help", "Show this help message")
    table.add_row("status", "Show engine status and provider info")
    table.add_row("history", "Show bounded turn history")
    table.add_row("audit", "Show audit log entries")
    table.add_row("clear", "Clear memory and turn history")
    table.add_row("exit / quit", "Shut down the engine")
    console.print(table)
    console.print("[dim]Any other input is sent through the 7-stage pipeline.[/dim]\n")


def print_result(result):
    """Styled table for successful results, panel for errors."""
    if result.is_secure:
        table = Table(
            title="Execution Result",
            border_style="green",
            title_style="bold green",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Field", width=18)
        table.add_column("Value")
        table.add_row("State ID", result.state_id)
        table.add_row("Status", "[green]SECURE[/green]")
        console.print(table)

        formatted = json.dumps(result.data, indent=2, ensure_ascii=False)
        syntax = Syntax(formatted, "json", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title="[bold white]Output Payload[/bold white]", border_style="green"))
        console.print()
    else:
        console.print(Panel(
            f"[bold red]Pipeline Error:[/bold red] {result.error_message}",
            border_style="red",
        ))


def _find_config():
    """Search for agent.brompt.yaml in CWD and parent directories."""
    from pathlib import Path
    candidates = [Path.cwd(), Path(__file__).resolve().parent.parent.parent]
    for base in candidates:
        cfg = base / "agent.brompt.yaml"
        if cfg.exists():
            return str(cfg)
    return "agent.brompt.yaml"


def main():
    boot_animation()

    try:
        from brompt.core import BromptEngine

        config_path = _find_config()
        console.print(f"[dim]Config: {config_path}[/dim]\n")
        engine = BromptEngine(config_path)
        provider_name = type(engine.provider).__name__ if engine.provider else "None (dry-run)"
        console.print(f"[dim]Provider: [bold]{provider_name}[/bold][/dim]")
        console.print("[dim]Type [bold]help[/bold] for commands, [bold]exit[/bold] to stop.[/dim]\n")

        while True:
            user_input = console.input("[bold yellow]⚡ brompt > [/bold yellow]").strip()
            if not user_input:
                continue
            cmd = user_input.lower()

            if cmd in ("exit", "quit"):
                console.print(Panel("[bold gray]Shutting down...[/bold gray]", border_style="dim"))
                break

            elif cmd == "help":
                print_help()

            elif cmd == "status":
                t = Table(title="Engine Status", border_style="cyan", show_header=True, header_style="bold cyan")
                t.add_column("Field", width=20)
                t.add_column("Value")
                t.add_row("Provider", provider_name)
                t.add_row("Provider Enabled", str(engine.provider is not None))
                t.add_row("State ID", engine.state_id)
                t.add_row("History Size", str(len(engine.memory.get_history())))
                t.add_row("Max History", str(engine.memory.max_turns))
                t.add_row("Audit Entries", str(len(engine.audit.read_all())))
                t.add_row("Audit Valid", str(engine.audit.verify()))
                console.print(t)
                console.print()

            elif cmd == "history":
                history = engine.memory.get_history()
                if not history:
                    console.print("[dim]No history yet.[/dim]\n")
                else:
                    t = Table(title="Turn History", border_style="purple", show_header=True, header_style="bold purple")
                    t.add_column("#", width=4)
                    t.add_column("Role", width=10)
                    t.add_column("Content")
                    for i, turn in enumerate(history, 1):
                        content = turn["content"][:80] + "..." if len(turn["content"]) > 80 else turn["content"]
                        t.add_row(str(i), turn["role"], content)
                    console.print(t)
                    console.print()

            elif cmd == "audit":
                entries = engine.audit.read_all()
                if not entries:
                    console.print("[dim]No audit entries yet.[/dim]\n")
                else:
                    t = Table(title="Audit Log", border_style="yellow", show_header=True, header_style="bold yellow")
                    t.add_column("#", width=4)
                    t.add_column("Event", width=18)
                    t.add_column("State ID", width=16)
                    t.add_column("Secure", width=8)
                    for i, e in enumerate(entries, 1):
                        secure = "[green]Yes[/green]" if e.get("is_secure") else "[red]No[/red]"
                        t.add_row(str(i), e["event"], e["state_id"][:16], secure)
                    console.print(t)
                    valid = engine.audit.verify()
                    color = "green" if valid else "red"
                    console.print(f"[{color}]Chain integrity: {'VALID' if valid else 'TAMPERED'}[/{color}]\n")

            elif cmd == "clear":
                engine.memory.clear()
                console.print("[green]Memory cleared.[/green]\n")

            else:
                print_result(engine.execute(user_input))

    except FileNotFoundError as e:
        console.print(f"[red]Config Error: {e}[/red]")
    except EOFError:
        console.print("[dim]Non-interactive mode detected. Exiting.[/dim]")
    except Exception as e:
        console.print(f"[red]Engine Error: {e}[/red]")


if __name__ == "__main__":
    main()
