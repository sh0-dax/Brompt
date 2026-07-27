"""Terminal User Interface for interacting with Brompt Engine."""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import time
import json
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
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


def main():
    boot_animation()

    try:
        from brompt.core import BromptEngine

        engine = BromptEngine("agent.brompt.yaml")
        console.print("[dim]Type [bold]exit[/bold] or [bold]quit[/bold] to stop.[/dim]\n")

        while True:
            user_input = console.input("[bold yellow]⚡ brompt > [/bold yellow]")
            if user_input.lower().strip() in ["exit", "quit"]:
                console.print(Panel("[bold gray]Shutting down...[/bold gray]", border_style="dim"))
                break
            print_result(engine.execute(user_input))

    except FileNotFoundError as e:
        console.print(f"[red]Config Error: {e}[/red]")
    except EOFError:
        console.print("[dim]Non-interactive mode detected. Exiting.[/dim]")
    except Exception as e:
        console.print(f"[red]Engine Error: {e}[/red]")


if __name__ == "__main__":
    main()
