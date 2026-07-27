"""Terminal User Interface for interacting with Brompt Engine."""

from rich.console import Console
from rich.panel import Panel
from brompt.core import BromptEngine

console = Console()


def main():
    console.print(Panel.fit("[bold cyan]Brompt Engine Interactive CLI v1.0.0[/bold cyan]"))

    try:
        engine = BromptEngine("agent.brompt.yaml")
        console.print("[green]Engine Subsystems Loaded Successfully.[/green]\n")

        while True:
            user_input = console.input("[yellow]Brompt Prompt > [/yellow]")
            if user_input.lower().strip() in ["exit", "quit"]:
                console.print("[bold gray]Exiting runtime interface...[/bold gray]")
                break

            result = engine.execute(user_input)
            if result.is_secure:
                console.print(f"[bold green]State ID:[/bold green] {result.state_id}")
                console.print(f"[bold white]Output Data Payload:[/bold white] {result.data}\n")
            else:
                console.print(f"[bold red]Pipeline Error:[/bold red] {result.error_message}\n")

    except Exception as e:
        console.print(f"[red]Engine Initialization Error: {e}[/red]")


if __name__ == "__main__":
    main()
