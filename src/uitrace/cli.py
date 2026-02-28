"""CLI entry point for uitrace."""
import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("list")
def list_windows():
    """List available windows."""
    raise typer.Exit(code=2)


@app.command("record")
def record():
    """Record UI interactions."""
    raise typer.Exit(code=2)


@app.command("play")
def play():
    """Play back recorded interactions."""
    raise typer.Exit(code=2)


@app.command("show")
def show():
    """Show trace summary."""
    raise typer.Exit(code=2)


@app.command("validate")
def validate():
    """Validate trace file."""
    raise typer.Exit(code=2)


@app.command("doctor")
def doctor():
    """Diagnose permissions and environment."""
    raise typer.Exit(code=2)


def main():
    """Entry point for console script."""
    app()
