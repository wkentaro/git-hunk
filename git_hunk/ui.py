"""Rich-based UI rendering for git-hunk.

Stdout  -> data (diff text, JSON, pretty tables)
Stderr  -> status messages and errors

TTY detection and NO_COLOR are handled automatically by rich.
"""

from collections import defaultdict

from rich.console import Console
from rich.text import Text

from .hunk import Hunk

out = Console(highlight=False)
err = Console(stderr=True, highlight=False)


def _append_stats(text: Text, hunk: Hunk) -> None:
    if hunk.additions:
        text.append(f"+{hunk.additions}", style="green")
    if hunk.additions and hunk.deletions:
        text.append(" ")
    if hunk.deletions:
        text.append(f"-{hunk.deletions}", style="red")


def print_hunk_list(hunks: list[Hunk]) -> None:
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
            _append_stats(line, hunk)
            out.print(line)
        out.print()


def print_hunk_diff(hunk: Hunk) -> None:
    out.print(f"[bold]{hunk.file}[/bold]  [dim]{hunk.id}[/dim]")
    out.print()
    line_num = 0
    for line in hunk.diff.split("\n"):
        if line.startswith("@@"):
            out.print(Text(line, style="cyan"))
        else:
            line_num += 1
            prefix = Text(f"{line_num:3d} ", style="dim")
            if line.startswith("+"):
                style = "green"
            elif line.startswith("-"):
                style = "red"
            else:
                style = "dim"
            out.print(Text.assemble(prefix, Text(line, style=style)))


def print_applied(hunks: list[Hunk], *, verb: str) -> None:
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
        _append_stats(line, hunk)
        err.print(line)


def print_error(msg: str) -> None:
    err.print(f"[bold red]error[/bold red]: {msg}")


HELP = """\
[bold]git-hunk[/bold] [dim]0.1.0[/dim]

Non-interactive git hunk tool for AI coding agents.

[bold]Usage:[/bold] git-hunk <command> [options]

[bold]Commands:[/bold]
  [bold cyan]list[/bold cyan]     List hunks
  [bold cyan]show[/bold cyan]     Show a specific hunk's diff
  [bold cyan]stage[/bold cyan]    Stage specific hunks
  [bold cyan]unstage[/bold cyan]  Unstage specific hunks
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
[bold]Usage:[/bold] git-hunk stage <id> [<id>...] [-l <lines>]

Stage one or more specific hunks. IDs support prefix matching.

[bold]Options:[/bold]
  [dim]-l <lines>  Stage only specific lines within a hunk (requires single id)[/dim]
             [dim]Examples: -l 3,5-7  (include)   -l ^3,^5-7  (exclude)[/dim]
"""

HELP_DISCARD = """\
[bold]Usage:[/bold] git-hunk discard <id> [<id>...] [-l <lines>]

Discard unstaged changes for one or more specific hunks (restore from HEAD).
IDs support prefix matching.

[bold]Options:[/bold]
  [dim]-l <lines>  Discard only specific lines within a hunk (requires single id)[/dim]
             [dim]Examples: -l 3,5-7  (include)   -l ^3,^5-7  (exclude)[/dim]
"""

HELP_UNSTAGE = """\
[bold]Usage:[/bold] git-hunk unstage <id> [<id>...] [-l <lines>]

Unstage one or more specific hunks (move from index back to working tree).
IDs support prefix matching.

[bold]Options:[/bold]
  [dim]-l <lines>  Unstage only specific lines within a hunk (requires single id)[/dim]
             [dim]Examples: -l 3,5-7  (include)   -l ^3,^5-7  (exclude)[/dim]
"""


def print_help(text: str) -> None:
    err.print(text)
