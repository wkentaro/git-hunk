"""Rich-based UI rendering for git-hunk.

Stdout  -> data (diff text, JSON, pretty tables)
Stderr  -> status messages and errors

Console objects are created at call time (not module level) so that
CliRunner's stream replacement works during testing.
"""

from collections import defaultdict

from rich.console import Console
from rich.text import Text

from .hunk import Hunk


def _out() -> Console:
    return Console(highlight=False)


def _err() -> Console:
    return Console(stderr=True, highlight=False)


def _append_stats(text: Text, hunk: Hunk) -> None:
    if hunk.additions:
        text.append(f"+{hunk.additions}", style="green")
    if hunk.additions and hunk.deletions:
        text.append(" ")
    if hunk.deletions:
        text.append(f"-{hunk.deletions}", style="red")


def _print_hunk_line(out: Console, hunk: Hunk) -> None:
    line = Text()
    line.append("  ")
    line.append(hunk.id, style="cyan")
    line.append("  ")
    line.append(hunk.header, style="dim")
    if hunk.context_before:
        line.append(f"  {hunk.context_before}", style="dim italic")
    line.append("  ")
    _append_stats(line, hunk)
    out.print(line)


def _print_file_group(
    out: Console, filepath: str, file_hunks: list[Hunk], *, color: str
) -> None:
    out.print(f"[{color}]{filepath}[/{color}]")
    for hunk in file_hunks:
        _print_hunk_line(out, hunk)


def _print_status_section(
    out: Console,
    hunks: list[Hunk],
    *,
    header: str,
    color: str,
    show_hunks: bool = True,
) -> None:
    if not hunks:
        return
    out.print(f"[dim]{header}[/dim]")
    by_file: dict[str, list[Hunk]] = defaultdict(list)
    for hunk in hunks:
        by_file[hunk.file].append(hunk)
    for i, (filepath, file_hunks) in enumerate(by_file.items()):
        if show_hunks:
            _print_file_group(out, filepath, file_hunks, color=color)
            if i < len(by_file) - 1:
                out.print()
        else:
            out.print(f"[{color}]{filepath}[/{color}]")


def print_hunk_list(hunks: list[Hunk]) -> None:
    if not hunks:
        _err().print("[dim]No hunks.[/dim]")
        return

    staged = [h for h in hunks if h.status == "staged"]
    unstaged = [h for h in hunks if h.status == "unstaged"]
    untracked = [h for h in hunks if h.status == "untracked"]

    out = _out()
    sections_printed = 0

    for section_hunks, header, color, show_hunks in [
        (staged, "staged:", "green", True),
        (unstaged, "unstaged:", "red", True),
        (untracked, "untracked:", "red", False),
    ]:
        if not section_hunks:
            continue
        if sections_printed > 0:
            out.print()
        _print_status_section(
            out, section_hunks, header=header, color=color, show_hunks=show_hunks
        )
        sections_printed += 1


def print_hunk_diff(hunk: Hunk) -> None:
    out = _out()
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
                style = ""
            out.print(Text.assemble(prefix, Text(line, style=style)))


def print_applied(hunks: list[Hunk], *, verb: str) -> None:
    err = _err()
    for hunk in hunks:
        line = Text()
        line.append(f"  {verb} ", style="bold green")
        line.append(hunk.id, style="cyan")
        line.append("  ")
        line.append(hunk.file, style="bold")
        line.append(f"  {hunk.header}", style="dim")
        if hunk.context_before:
            line.append(f"  {hunk.context_before}", style="dim italic")
        line.append("  ")
        _append_stats(line, hunk)
        err.print(line)


def print_error(
    msg: str,
    *,
    tip: str | None = None,
    usage: str | None = None,
) -> None:
    err = _err()
    err.print(f"[bold red]error[/bold red]: {msg}")
    if tip:
        err.print(f"\n  [green]tip[/green]: {tip}")
    if usage:
        err.print(f"\n{usage}")
        err.print("\nFor more information, try '[bold cyan]--help[/bold cyan]'.")


def print_version(version: str) -> None:
    _err().print(f"git-hunk [dim]{version}[/dim]")


_LINE_OPTS = """\
[bold green]Options:[/bold green]
  [bold cyan]-l[/bold cyan] [cyan]<lines>[/cyan]  Select specific lines within a hunk (requires single id)
             Examples: -l 3,5-7  (include)   -l ^3,^5-7  (exclude)"""  # noqa: E501

USAGE = "[bold green]Usage:[/bold green] [bold cyan]git-hunk[/bold cyan] [cyan]<COMMAND>[/cyan]"  # noqa: E501
USAGE_SHOW = "[bold green]Usage:[/bold green] [bold cyan]git-hunk show[/bold cyan] [cyan]<id>[/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501
USAGE_STAGE = "[bold green]Usage:[/bold green] [bold cyan]git-hunk stage[/bold cyan] [cyan]<id>[/cyan] [cyan][<id>...][/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501
USAGE_UNSTAGE = "[bold green]Usage:[/bold green] [bold cyan]git-hunk unstage[/bold cyan] [cyan]<id>[/cyan] [cyan][<id>...][/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501
USAGE_DISCARD = "[bold green]Usage:[/bold green] [bold cyan]git-hunk discard[/bold cyan] [cyan]<id>[/cyan] [cyan][<id>...][/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501

HELP = f"""\
Non-interactive git hunk staging for AI agents.

{USAGE}

[bold green]Commands:[/bold green]
  [bold cyan]list[/bold cyan]     List hunks
  [bold cyan]show[/bold cyan]     Show a specific hunk's diff
  [bold cyan]stage[/bold cyan]    Stage specific hunks
  [bold cyan]unstage[/bold cyan]  Unstage specific hunks
  [bold cyan]discard[/bold cyan]  Discard specific hunks (restore from HEAD)

[bold green]Options:[/bold green]
  [bold cyan]-h[/bold cyan], [bold cyan]--help[/bold cyan]     Print help
  [bold cyan]-V[/bold cyan], [bold cyan]--version[/bold cyan]  Print version"""

HELP_LIST = """\
List hunks (unstaged, staged, and untracked by default).

[bold green]Usage:[/bold green] [bold cyan]git-hunk list[/bold cyan] [cyan][OPTIONS][/cyan] [cyan][<file>...][/cyan]

[bold green]Options:[/bold green]
  [bold cyan]--staged[/bold cyan]      Show only staged hunks
  [bold cyan]--unstaged[/bold cyan]    Show only unstaged hunks
  [bold cyan]--json[/bold cyan]        Output as JSON"""  # noqa: E501

HELP_SHOW = f"""\
Show the diff for a specific hunk. IDs support prefix matching.

{USAGE_SHOW}

[bold green]Options:[/bold green]
  [bold cyan]--staged[/bold cyan]    Look in staged hunks"""

HELP_STAGE = f"""\
Stage one or more specific hunks. IDs support prefix matching.

{USAGE_STAGE}

{_LINE_OPTS}"""

HELP_DISCARD = f"""\
Discard unstaged changes for one or more specific hunks (restore from HEAD).
IDs support prefix matching.

{USAGE_DISCARD}

{_LINE_OPTS}"""

HELP_UNSTAGE = f"""\
Unstage one or more specific hunks (move from index back to working tree).
IDs support prefix matching.

{USAGE_UNSTAGE}

{_LINE_OPTS}"""


def print_help(text: str) -> None:
    _err().print(text)
