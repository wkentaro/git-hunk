"""CLI entry point for git-hunk."""

import json
import sys
from typing import List, Optional

from .git import apply_patch, get_diff
from .hunk import Hunk, parse_diff
from .patch import build_patch


def _get_hunks(staged: bool, files: Optional[List[str]] = None) -> List[Hunk]:
    diff = get_diff(staged=staged, files=files)
    return parse_diff(diff)


def _find_hunks_by_ids(hunks: List[Hunk], ids: List[str]) -> List[Hunk]:
    hunk_map = {h.id: h for h in hunks}
    found = []
    for hunk_id in ids:
        # Support prefix matching
        matches = [h for id_, h in hunk_map.items() if id_.startswith(hunk_id)]
        if len(matches) == 0:
            print(f"error: hunk '{hunk_id}' not found", file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            print(f"error: ambiguous hunk id '{hunk_id}'", file=sys.stderr)
            sys.exit(1)
        found.append(matches[0])
    return found


def cmd_list(args: List[str]) -> None:
    staged = "--staged" in args
    files = [a for a in args if not a.startswith("-")]
    hunks = _get_hunks(staged=staged, files=files or None)
    print(json.dumps([h.to_dict() for h in hunks], indent=2))


def cmd_show(args: List[str]) -> None:
    if not args:
        print("error: git-hunk show requires a hunk id", file=sys.stderr)
        sys.exit(1)

    hunk_id = args[0]
    staged = "--staged" in args

    hunks = _get_hunks(staged=staged)
    found = _find_hunks_by_ids(hunks, [hunk_id])
    print(found[0].diff)


def cmd_stage(args: List[str]) -> None:
    if not args:
        print("error: git-hunk stage requires at least one hunk id", file=sys.stderr)
        sys.exit(1)

    hunks = _get_hunks(staged=False)
    selected = _find_hunks_by_ids(hunks, args)
    diff_output = get_diff(staged=False)
    patch = build_patch(selected, diff_output)
    apply_patch(patch, cached=True)
    print(f"Staged {len(selected)} hunk(s)", file=sys.stderr)


def cmd_discard(args: List[str]) -> None:
    if not args:
        print("error: git-hunk discard requires at least one hunk id", file=sys.stderr)
        sys.exit(1)

    hunks = _get_hunks(staged=False)
    selected = _find_hunks_by_ids(hunks, args)
    diff_output = get_diff(staged=False)
    patch = build_patch(selected, diff_output)
    apply_patch(patch, reverse=True)
    print(f"Discarded {len(selected)} hunk(s)", file=sys.stderr)


COMMANDS = {
    "list": cmd_list,
    "show": cmd_show,
    "stage": cmd_stage,
    "discard": cmd_discard,
}

USAGE = """\
usage: git-hunk <command> [<args>]

commands:
  list [--staged] [<file>...]   List hunks as JSON
  show <id> [--staged]          Show a specific hunk's diff
  stage <id> [<id>...]          Stage specific hunks
  discard <id> [<id>...]        Discard specific hunks (restore from HEAD)
"""


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(USAGE, end="")
        sys.exit(0)

    if args[0] in ("-V", "--version"):
        from . import __version__
        print(f"git-hunk {__version__}")
        sys.exit(0)

    cmd = args[0]
    if cmd not in COMMANDS:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        print(USAGE, end="", file=sys.stderr)
        sys.exit(1)

    COMMANDS[cmd](args[1:])
