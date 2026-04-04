import json
import sys

from .git import apply_patch
from .git import get_diff
from .hunk import Hunk
from .hunk import parse_diff
from .lines import filter_hunk_lines
from .lines import parse_line_spec
from .patch import build_patch
from .ui import HELP
from .ui import HELP_DISCARD
from .ui import HELP_LIST
from .ui import HELP_SHOW
from .ui import HELP_STAGE
from .ui import HELP_UNSTAGE
from .ui import err
from .ui import print_applied
from .ui import print_error
from .ui import print_help
from .ui import print_hunk_diff
from .ui import print_hunk_list


def _get_hunks(staged: bool, files: list[str] | None = None) -> list[Hunk]:
    return parse_diff(get_diff(staged=staged, files=files))


def _find_hunks_by_ids(hunks: list[Hunk], ids: list[str]) -> list[Hunk]:
    found = []
    for hunk_id in ids:
        matches = [h for h in hunks if h.id.startswith(hunk_id)]
        if len(matches) == 0:
            print_error(f"hunk '{hunk_id}' not found")
            sys.exit(1)
        if len(matches) > 1:
            print_error(f"ambiguous hunk id '{hunk_id}' — be more specific")
            sys.exit(1)
        found.append(matches[0])
    return found


def _extract_line_spec(args: list[str]) -> tuple:
    remaining = []
    line_spec = None
    i = 0
    while i < len(args):
        if args[i] == "-l" and i + 1 < len(args):
            line_spec = args[i + 1]
            i += 2
        elif args[i].startswith("-l") and len(args[i]) > 2:
            line_spec = args[i][2:]
            i += 1
        else:
            remaining.append(args[i])
            i += 1
    return remaining, line_spec


def _apply_line_filter(hunks: list[Hunk], line_spec: str | None) -> list[Hunk]:
    if line_spec is None:
        return hunks
    if len(hunks) != 1:
        print_error("line selection (-l) requires exactly one hunk id")
        sys.exit(1)
    try:
        lines, exclude = parse_line_spec(line_spec)
        return [filter_hunk_lines(hunks[0], lines, exclude=exclude)]
    except ValueError as exc:
        print_error(str(exc))
        sys.exit(1)


def _run_patch_command(
    args: list[str],
    *,
    help_text: str,
    command_name: str,
    staged: bool,
    cached: bool,
    reverse: bool,
    verb: str,
) -> None:
    if "-h" in args or "--help" in args:
        print_help(help_text)
        return

    args, line_spec = _extract_line_spec(args)
    ids = [a for a in args if not a.startswith("-")]
    if not ids:
        print_error(f"{command_name} requires at least one hunk id")
        print_help(help_text)
        sys.exit(1)

    hunks = _get_hunks(staged=staged)
    selected = _find_hunks_by_ids(hunks, ids)
    selected = _apply_line_filter(selected, line_spec)
    diff_output = get_diff(staged=staged)
    patch = build_patch(selected, diff_output)

    try:
        apply_patch(patch, cached=cached, reverse=reverse)
    except RuntimeError as exc:
        print_error(str(exc))
        sys.exit(1)

    print_applied(selected, verb=verb)


def cmd_list(args: list[str]) -> None:
    if "-h" in args or "--help" in args:
        print_help(HELP_LIST)
        return

    staged = "--staged" in args
    force_json = "--json" in args
    files = [a for a in args if not a.startswith("-")]

    hunks = _get_hunks(staged=staged, files=files or None)

    if force_json or not sys.stdout.isatty():
        print(json.dumps([h.to_dict() for h in hunks], indent=2))
    else:
        print_hunk_list(hunks)


def cmd_show(args: list[str]) -> None:
    if "-h" in args or "--help" in args:
        print_help(HELP_SHOW)
        return

    positional = [a for a in args if not a.startswith("-")]
    if not positional:
        print_error("show requires a hunk id")
        print_help(HELP_SHOW)
        sys.exit(1)

    hunk_id = positional[0]
    staged = "--staged" in args

    hunks = _get_hunks(staged=staged)
    (hunk,) = _find_hunks_by_ids(hunks, [hunk_id])

    if sys.stdout.isatty():
        print_hunk_diff(hunk)
    else:
        lines = hunk.diff.split("\n")
        line_num = 0
        for line in lines:
            if line.startswith("@@"):
                print(line)
            else:
                line_num += 1
                print(f"{line_num}: {line}")


def cmd_stage(args: list[str]) -> None:
    _run_patch_command(
        args,
        help_text=HELP_STAGE,
        command_name="stage",
        staged=False,
        cached=True,
        reverse=False,
        verb="staged",
    )


def cmd_unstage(args: list[str]) -> None:
    _run_patch_command(
        args,
        help_text=HELP_UNSTAGE,
        command_name="unstage",
        staged=True,
        cached=True,
        reverse=True,
        verb="unstaged",
    )


def cmd_discard(args: list[str]) -> None:
    _run_patch_command(
        args,
        help_text=HELP_DISCARD,
        command_name="discard",
        staged=False,
        cached=False,
        reverse=True,
        verb="discarded",
    )


COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "stage": cmd_stage,
    "unstage": cmd_unstage,
    "discard": cmd_discard,
}


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print_help(HELP)
        sys.exit(0)

    if args[0] in ("-V", "--version"):
        from . import __version__

        err.print(f"git-hunk [dim]{__version__}[/dim]")
        sys.exit(0)

    cmd = args[0]
    if cmd not in COMMANDS:
        print_error(f"unknown command '{cmd}'")
        print_help(HELP)
        sys.exit(1)

    try:
        COMMANDS[cmd](args[1:])
    except KeyboardInterrupt:
        sys.exit(130)
