"""Rich-based UI rendering for git-hunk.

Stdout  → data (diff text, JSON, pretty tables)
Stderr  → status messages and errors

TTY detection and NO_COLOR are handled automatically by rich.
"""

import sys
from collections import defaultdict
from typing import List

from rich.console import Console
from rich.text import Text

from .hunk import Hunk

# Data goes to stdout; status/errors go to stderr.
# highlight=False: don't auto-highlight arbitrary strings (we color explicitly).
out = Console(highlight=False)
err = Console(stderr=True, highlight=False)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def print_hunk_list(hunks: List[Hunk]) -> None:
    """Print hunks grouped by file — human-readable TTY format."""
    if not hunks:
        err.print("[dim]No hunks.[/dim]")
        return

    by_file: dict = defaultdict(list)
    for hunk in hunks:
        by_file[hunk.file].append(hunk)

    for filepath, file_hunks in by_file.items():
        out.print(f"[bold]{filepath}[/bold]")
        for hunk in file_hunks:
            line = Text()
            line.append("  ")
            line.append(hunk.id, style="bold cyan")
            line.append("  ")
            line.append(hunk.header, style="dim")
            if hunk.context_before:
                line.append(f"  {hunk.context_before}", style="dim italic")
            line.append("  ")
            if hunk.additions:
                line.append(f"+{hunk.additions}", style="green")
            if hunk.additions and hunk.deletions:
                line.append(" ")
            if hunk.deletions:
                line.append(f"-{hunk.deletions}", style="red")
            out.print(line)
        out.print()


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def print_hunk_diff(hunk: Hunk) -> None:
    """Print a single hunk diff with git-style colors."""
    out.print(f"[bold]{hunk.file}[/bold]  [dim]{hunk.id}[/dim]")
    out.print()
    for line in hunk.diff.split("\n"):
        if line.startswith("@@"):
            out.print(Text(line, style="cyan"))
        elif line.startswith("+"):
            out.print(Text(line, style="green"))
        elif line.startswith("-"):
            out.print(Text(line, style="red"))
        elif line.startswith("\\"):
            out.print(Text(line, style="dim"))
        else:
            # Context line — dim so additions/deletions stand out
            out.print(Text(line, style="dim"))


# ---------------------------------------------------------------------------
# stage / discard
# ---------------------------------------------------------------------------


def print_applied(hunks: List[Hunk], verb: str) -> None:
    """Print a ✓ confirmation line per hunk to stderr."""
    for hunk in hunks:
        line = Text()
        line.append(f"  {verb} ", style="bold green")
        line.append(hunk.id, style="bold cyan")
        line.append("  ")
        line.append(hunk.file, style="bold")
        line.append(f"  {hunk.header}", style="dim")
        if hunk.context_before:
            line.append(f"  {hunk.context_before}", style="dim italic")
        line.append("  ")
        if hunk.additions:
            line.append(f"+{hunk.additions}", style="green")
        if hunk.additions and hunk.deletions:
            line.append(" ")
        if hunk.deletions:
            line.append(f"-{hunk.deletions}", style="red")
        err.print(line)


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------


def print_error(msg: str) -> None:
    err.print(f"[bold red]error[/bold red]: {msg}")


def print_warning(msg: str) -> None:
    err.print(f"[bold yellow]warning[/bold yellow]: {msg}")


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------

HELP = """\
[bold]git-hunk[/bold] [dim]0.1.0[/dim]

Non-interactive git hunk tool for AI coding agents.

[bold]Usage:[/bold] git-hunk <command> [options]

[bold]Commands:[/bold]
  [bold cyan]list[/bold cyan]     List hunks
  [bold cyan]show[/bold cyan]     Show a specific hunk's diff
  [bold cyan]stage[/bold cyan]    Stage specific hunks
  [bold cyan]discard[/bold cyan]  Discard specific hunks (restore from HEAD)

[bold]Options:[/bold]
  [dim]-h, --help     Show this message and exit[/dim]
  [dim]-V, --version  Show version and exit[/dim]

Run [italic]git-hunk <command> --help[/italic] for command-specific help.
"""

HELP_LIST = """\
[bold]Usage:[/bold] git-hunk list [--staged] [--json] [<file>...]

List hunks. Outputs JSON when stdout is not a TTY (pipe-friendly).

[bold]Options:[/bold]
  [dim]--staged    List staged hunks instead of unstaged[/dim]
  [dim]--json      Force JSON output even on a TTY[/dim]
"""

HELP_SHOW = """\
[bold]Usage:[/bold] git-hunk show <id> [--staged]

Show the diff for a specific hunk. IDs support prefix matching.

[bold]Options:[/bold]
  [dim]--staged    Look in staged hunks[/dim]
"""

HELP_STAGE = """\
[bold]Usage:[/bold] git-hunk stage <id> [<id>...]

Stage one or more specific hunks. IDs support prefix matching.
"""

HELP_DISCARD = """\
[bold]Usage:[/bold] git-hunk discard <id> [<id>...]

Discard unstaged changes for one or more specific hunks (restore from HEAD).
IDs support prefix matching.
"""


def print_help(text: str) -> None:
    err.print(text)
