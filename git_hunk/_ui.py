"""Rich-based UI rendering for git-hunk.

Stdout  -> data (diff text, JSON, pretty tables)
Stderr  -> status messages and errors

Console objects are created at call time (not module level) so that
CliRunner's stream replacement works during testing.
"""

from collections import defaultdict
from typing import Final

from rich.console import Console
from rich.markup import escape
from rich.rule import Rule
from rich.text import Text

from ._hunk import Hunk
from ._hunk import is_no_newline_marker
from ._skills import Skill


def _out() -> Console:
    return Console(highlight=False)


def _err() -> Console:
    return Console(stderr=True, highlight=False)


def _safe(text: str) -> str:
    # git output decoded with surrogateescape (see _git.run_git) may carry lone
    # surrogates for non-UTF-8 bytes; backslash-escape them so writing to a
    # strict stdout does not raise UnicodeEncodeError.
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


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
    line.append(_safe(hunk.header), style="dim")
    if hunk.context_before:
        line.append(f"  {_safe(hunk.context_before)}", style="dim italic")
    line.append("  ")
    _append_stats(line, hunk)
    out.print(line)


def _print_file_group(
    out: Console, filepath: str, file_hunks: list[Hunk], *, color: str
) -> None:
    out.print(f"[{color}]{escape(_safe(filepath))}[/{color}]")
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
            out.print(f"[{color}]{escape(_safe(filepath))}[/{color}]")


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


def _print_hunk_diff(out: Console, hunk: Hunk) -> None:
    out.print(f"[bold]{escape(_safe(hunk.file))}[/bold]  [dim]{escape(hunk.id)}[/dim]")
    if not hunk.diff:
        out.print(Text(_safe(hunk.header), style="dim"))
        return
    line_num = 0
    for line in hunk.diff.split("\n"):
        if line.startswith("@@"):
            out.print(Text(_safe(line), style="cyan"))
        elif is_no_newline_marker(line):
            out.print(Text("    " + line, style="dim"))
        else:
            line_num += 1
            prefix = Text(f"{line_num:3d} ", style="dim")
            if line.startswith("+"):
                style = "green"
            elif line.startswith("-"):
                style = "red"
            else:
                style = ""
            out.print(Text.assemble(prefix, Text(_safe(line), style=style)))


def print_skill_list(skills: list[Skill]) -> None:
    if not skills:
        _err().print("[dim]No skills.[/dim]")
        return
    out = _out()
    width = max(len(skill.name) for skill in skills)
    for skill in skills:
        summary = skill.description.split("\n", 1)[0]
        pad = " " * (width - len(skill.name) + 2)
        line = Text.assemble(Text(skill.name, style="cyan"), Text(pad + summary, "dim"))
        out.print(line, no_wrap=True, overflow="ellipsis")


def print_hunk_diffs(hunks: list[Hunk]) -> None:
    out = _out()
    for i, hunk in enumerate(hunks):
        if i > 0:
            out.print(Rule(style="dim"))
        _print_hunk_diff(out, hunk)


def print_applied(hunks: list[Hunk], *, verb: str) -> None:
    err = _err()
    for hunk in hunks:
        line = Text()
        line.append(f"  {verb} ", style="bold green")
        line.append(hunk.id, style="cyan")
        line.append("  ")
        line.append(_safe(hunk.file), style="bold")
        line.append(f"  {_safe(hunk.header)}", style="dim")
        if hunk.context_before:
            line.append(f"  {_safe(hunk.context_before)}", style="dim italic")
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
    err.print(f"[bold red]error[/bold red]: {escape(_safe(msg))}")
    if tip:
        err.print(f"\n  [green]tip[/green]: {escape(_safe(tip))}")
    if usage:
        err.print(f"\n{usage}")
        err.print("\nFor more information, try '[bold cyan]--help[/bold cyan]'.")


def print_version(version: str) -> None:
    _err().print(f"git-hunk [dim]{version}[/dim]")


_LINE_OPTS = """\
[bold green]Options:[/bold green]
  [bold cyan]-l[/bold cyan] [cyan]<lines>[/cyan]  Select specific lines within a hunk (requires exactly one hunk)
             e.g.: -l 3,5-7  (include)   -l ^3,^5-7  (exclude)
  [bold cyan]--dry-run[/bold cyan]   Report what would change without touching the index or working tree"""  # noqa: E501

USAGE = "[bold green]Usage:[/bold green] [bold cyan]git-hunk[/bold cyan] [cyan]<COMMAND>[/cyan]"  # noqa: E501
USAGE_SHOW = "[bold green]Usage:[/bold green] [bold cyan]git-hunk show[/bold cyan] [cyan][<id>...][/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501
USAGE_STAGE = "[bold green]Usage:[/bold green] [bold cyan]git-hunk stage[/bold cyan] [cyan]<id|file>[/cyan] [cyan][<id|file>...][/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501
USAGE_UNSTAGE = "[bold green]Usage:[/bold green] [bold cyan]git-hunk unstage[/bold cyan] [cyan]<id|file>[/cyan] [cyan][<id|file>...][/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501
USAGE_DISCARD = "[bold green]Usage:[/bold green] [bold cyan]git-hunk discard[/bold cyan] [cyan]<id|file>[/cyan] [cyan][<id|file>...][/cyan] [cyan][OPTIONS][/cyan]"  # noqa: E501
USAGE_SKILLS = "[bold green]Usage:[/bold green] [bold cyan]git-hunk skills[/bold cyan] [cyan][SUBCOMMAND][/cyan] [cyan][<name>...][/cyan]"  # noqa: E501


def _format_examples(rows: list[tuple[str, str]]) -> str:
    width = max(len(command) for command, _ in rows)
    lines = ["[bold green]Examples:[/bold green]"]
    for command, comment in rows:
        pad = " " * (width - len(command) + 2)
        lines.append(f"  [cyan]{command}[/cyan]{pad}[dim]# {comment}[/dim]")
    return "\n".join(lines)


_EXAMPLES_LIST: Final = [
    ("git-hunk list", "Unstaged, staged, and untracked"),
    ("git-hunk list --unstaged", "Unstaged hunks only"),
    ("git-hunk list --staged", "Staged hunks only"),
    ("git-hunk list src/foo.py", "Specific files only"),
    ("git-hunk list --json", "JSON output for scripting"),
]
_EXAMPLES_SHOW: Final = [
    ("git-hunk show", "Show all hunks"),
    ("git-hunk show d161935", "Show a single hunk"),
    ("git-hunk show d161935 a3f82c1", "Show multiple hunks"),
    ("git-hunk show --staged", "Show all staged hunks"),
]
_EXAMPLES_STAGE: Final = [
    ("git-hunk stage d161935", "Stage a hunk"),
    ("git-hunk stage d161935 a3f82c1", "Stage multiple hunks"),
    ("git-hunk stage src/foo.py", "Stage every hunk in a file"),
    ("git-hunk stage d161935 -l 3,5-7", "Stage specific lines only"),
    ("git-hunk stage d161935 --dry-run", "Preview without changing anything"),
]
_EXAMPLES_UNSTAGE: Final = [
    ("git-hunk unstage d161935", "Move a hunk back to working tree"),
    ("git-hunk unstage src/foo.py", "Unstage every hunk in a file"),
    ("git-hunk unstage d161935 -l 3,5-7", "Unstage specific lines only"),
    ("git-hunk unstage d161935 --dry-run", "Preview without changing anything"),
]
_EXAMPLES_DISCARD: Final = [
    ("git-hunk discard d161935", "Restore a hunk from HEAD"),
    ("git-hunk discard src/foo.py", "Discard every hunk in a file"),
    ("git-hunk discard d161935 -l ^3,^5-7", "Discard excluding specific lines"),
    ("git-hunk discard d161935 --dry-run", "Preview without changing anything"),
]
_EXAMPLES_SKILLS: Final = [
    ("git-hunk skills", "List available skills"),
    ("git-hunk skills get core", "Load the core usage guide"),
    ("git-hunk skills path", "Print the skills directory path"),
]
_EXAMPLES_ALL: Final = (
    _EXAMPLES_LIST
    + _EXAMPLES_SHOW
    + _EXAMPLES_STAGE
    + _EXAMPLES_UNSTAGE
    + _EXAMPLES_DISCARD
)

HELP = f"""\
Non-interactive git hunk staging for AI agents.

{USAGE}

[bold green]Start here (for AI agents):[/bold green]
  [cyan]git-hunk skills get core[/cyan]

  Skills ship with the CLI (always version-matched) and include the full
  workflow, partial-hunk syntax, and copy-paste examples. Prefer this over
  guessing commands from flags alone.

[bold green]Commands:[/bold green]
  [bold cyan]list[/bold cyan]     List hunks
  [bold cyan]show[/bold cyan]     Show diff for one or more hunks
  [bold cyan]stage[/bold cyan]    Stage specific hunks
  [bold cyan]unstage[/bold cyan]  Unstage specific hunks
  [bold cyan]discard[/bold cyan]  Discard specific hunks (restore from HEAD)
  [bold cyan]skills[/bold cyan]   Load bundled skill content for AI agents

[bold green]Options:[/bold green]
  [bold cyan]-h[/bold cyan], [bold cyan]--help[/bold cyan]     Print help
  [bold cyan]-V[/bold cyan], [bold cyan]--version[/bold cyan]  Print version

{_format_examples(_EXAMPLES_ALL)}"""

HELP_LIST = f"""\
List hunks (unstaged, staged, and untracked by default).

[bold green]Usage:[/bold green] [bold cyan]git-hunk list[/bold cyan] [cyan][OPTIONS][/cyan] [cyan][<file>...][/cyan]

[bold green]Options:[/bold green]
  [bold cyan]--staged[/bold cyan]      Show only staged hunks
  [bold cyan]--unstaged[/bold cyan]    Show only unstaged hunks
  [bold cyan]--json[/bold cyan]        Output as JSON

{_format_examples(_EXAMPLES_LIST)}"""  # noqa: E501

HELP_SHOW = f"""\
Show the diff for one or more hunks. Shows all hunks when no IDs given.
IDs support prefix matching.

{USAGE_SHOW}

[bold green]Options:[/bold green]
  [bold cyan]--staged[/bold cyan]     Show only staged hunks
  [bold cyan]--unstaged[/bold cyan]   Show only unstaged hunks

{_format_examples(_EXAMPLES_SHOW)}"""

HELP_STAGE = f"""\
Stage one or more specific hunks. IDs support prefix matching.

{USAGE_STAGE}

{_LINE_OPTS}

{_format_examples(_EXAMPLES_STAGE)}"""

HELP_DISCARD = f"""\
Discard unstaged changes for one or more specific hunks (restore from HEAD).
IDs support prefix matching.

{USAGE_DISCARD}

{_LINE_OPTS}

{_format_examples(_EXAMPLES_DISCARD)}"""

HELP_UNSTAGE = f"""\
Unstage one or more specific hunks (move from index back to working tree).
IDs support prefix matching.

{USAGE_UNSTAGE}

{_LINE_OPTS}

{_format_examples(_EXAMPLES_UNSTAGE)}"""

HELP_SKILLS = f"""\
List and retrieve bundled skill content. Skills always match the installed
git-hunk version, so prefer them over guessing commands from flags alone.

{USAGE_SKILLS}

[bold green]Subcommands:[/bold green]
  [bold cyan]list[/bold cyan]             List available skills (default)
  [bold cyan]get[/bold cyan] [cyan]<name>[/cyan]       Output a skill's full content
  [bold cyan]path[/bold cyan] [cyan][<name>][/cyan]    Print the skill directory path

[bold green]Options:[/bold green]
  [bold cyan]--json[/bold cyan]        Output as JSON

{_format_examples(_EXAMPLES_SKILLS)}"""


def print_help(text: str) -> None:
    _err().print(text)
