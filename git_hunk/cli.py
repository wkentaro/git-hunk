"""CLI entry point for git-hunk."""

import json
import sys
from typing import List, Optional

from .git import apply_patch, get_diff
from .hunk import Hunk, parse_diff
from .patch import build_patch
from .ui import (
    HELP,
    HELP_DISCARD,
    HELP_LIST,
    HELP_SHOW,
    HELP_STAGE,
    err,
    out,
    print_applied,
    print_error,
    print_help,
    print_hunk_diff,
    print_hunk_list,
)


def _get_hunks(staged: bool, files: Optional[List[str]] = None) -> List[Hunk]:
    diff = get_diff(staged=staged, files=files)
    return parse_diff(diff)


def _find_hunks_by_ids(hunks: List[Hunk], ids: List[str]) -> List[Hunk]:
    """Resolve hunk IDs (with prefix matching) or exit with an error."""
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


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_list(args: List[str]) -> None:
    if "-h" in args or "--help" in args:
        print_help(HELP_LIST)
        return

    staged = "--staged" in args
    force_json = "--json" in args
    files = [a for a in args if not a.startswith("-")]

    hunks = _get_hunks(staged=staged, files=files or None)

    # JSON when: explicitly requested, or stdout is not a TTY (pipe/agent mode)
    if force_json or not sys.stdout.isatty():
        print(json.dumps([h.to_dict() for h in hunks], indent=2))
    else:
        print_hunk_list(hunks)


def cmd_show(args: List[str]) -> None:
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
        # Plain diff text when piped — compatible with patch(1) etc.
        print(hunk.diff)


def cmd_stage(args: List[str]) -> None:
    if "-h" in args or "--help" in args:
        print_help(HELP_STAGE)
        return

    ids = [a for a in args if not a.startswith("-")]
    if not ids:
        print_error("stage requires at least one hunk id")
        print_help(HELP_STAGE)
        sys.exit(1)

    hunks = _get_hunks(staged=False)
    selected = _find_hunks_by_ids(hunks, ids)
    diff_output = get_diff(staged=False)
    patch = build_patch(selected, diff_output)

    try:
        apply_patch(patch, cached=True)
    except RuntimeError as exc:
        print_error(str(exc))
        sys.exit(1)

    print_applied(selected, verb="staged")


def cmd_discard(args: List[str]) -> None:
    if "-h" in args or "--help" in args:
        print_help(HELP_DISCARD)
        return

    ids = [a for a in args if not a.startswith("-")]
    if not ids:
        print_error("discard requires at least one hunk id")
        print_help(HELP_DISCARD)
        sys.exit(1)

    hunks = _get_hunks(staged=False)
    selected = _find_hunks_by_ids(hunks, ids)
    diff_output = get_diff(staged=False)
    patch = build_patch(selected, diff_output)

    try:
        apply_patch(patch, reverse=True)
    except RuntimeError as exc:
        print_error(str(exc))
        sys.exit(1)

    print_applied(selected, verb="discarded")


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "stage": cmd_stage,
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
