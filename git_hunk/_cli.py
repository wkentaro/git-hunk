import json
from dataclasses import replace

import click

from . import __version__
from ._git import apply_patch
from ._git import discard_files
from ._git import get_diff
from ._git import get_untracked_files
from ._git import is_git_repo
from ._git import stage_files
from ._git import unstage_files
from ._hunk import Hunk
from ._hunk import parse_diff
from ._lines import filter_hunk_lines
from ._lines import parse_line_spec
from ._patch import build_patch
from ._ui import HELP
from ._ui import HELP_DISCARD
from ._ui import HELP_LIST
from ._ui import HELP_SHOW
from ._ui import HELP_STAGE
from ._ui import HELP_UNSTAGE
from ._ui import USAGE
from ._ui import USAGE_DISCARD
from ._ui import USAGE_STAGE
from ._ui import USAGE_UNSTAGE
from ._ui import print_applied
from ._ui import print_error
from ._ui import print_help
from ._ui import print_hunk_diffs
from ._ui import print_hunk_list
from ._ui import print_version


class CliError(Exception):
    def __init__(
        self,
        message: str,
        *,
        tip: str | None = None,
        usage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tip = tip
        self.usage = usage


class CliGroup(click.Group):
    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            cmd_name = args[0] if args else ""
            raise CliError(
                f"unrecognized subcommand '{cmd_name}'", usage=USAGE
            ) from None

    def invoke(self, ctx: click.Context) -> None:
        try:
            super().invoke(ctx)
        except CliError as exc:
            print_error(str(exc), tip=exc.tip, usage=exc.usage)
            ctx.exit(2 if exc.usage else 1)
        except KeyboardInterrupt:
            ctx.exit(130)


def _require_git_repo() -> None:
    if not is_git_repo():
        raise CliError("not a git repository")


def _get_hunks(staged: bool, files: list[str] | None = None) -> tuple[list[Hunk], str]:
    _require_git_repo()
    diff_output = get_diff(staged=staged, files=files)
    hunks = parse_diff(diff_output)
    status = "staged" if staged else "unstaged"
    hunks = [replace(h, status=status) for h in hunks]
    return hunks, diff_output


def _find_hunks_by_ids(hunks: list[Hunk], ids: list[str]) -> list[Hunk]:
    found = []
    for hunk_id in ids:
        matches = [h for h in hunks if h.id.startswith(hunk_id)]
        if len(matches) == 0:
            available = [h.id for h in hunks]
            tip = f"available hunk ids: {', '.join(available)}" if available else None
            raise CliError(f"hunk '{hunk_id}' not found", tip=tip)
        if len(matches) > 1:
            candidates = ", ".join(m.id for m in matches)
            raise CliError(
                f"ambiguous hunk id '{hunk_id}'",
                tip=f"matches: {candidates}",
            )
        found.append(matches[0])
    return found


def _apply_line_filter(hunks: list[Hunk], line_spec: str | None) -> list[Hunk]:
    if line_spec is None:
        return hunks
    if len(hunks) != 1:
        raise CliError("line selection (-l) requires exactly one hunk id")
    try:
        lines, exclude = parse_line_spec(line_spec)
        return [filter_hunk_lines(hunks[0], lines, exclude=exclude)]
    except ValueError as exc:
        raise CliError(str(exc)) from exc


def _is_binary_hunk(hunk: Hunk) -> bool:
    return hunk.header == "Binary file"


def _run_patch_command(
    ids: list[str],
    line_spec: str | None,
    *,
    usage: str,
    command_name: str,
    staged: bool,
    cached: bool,
    reverse: bool,
    verb: str,
) -> None:
    if not ids:
        raise CliError(
            f"{command_name} requires at least one hunk id",
            usage=usage,
        )

    hunks, diff_output = _get_hunks(staged=staged)
    selected = _find_hunks_by_ids(hunks, ids)
    selected = _apply_line_filter(selected, line_spec)

    binary = [h for h in selected if _is_binary_hunk(h)]
    text = [h for h in selected if not _is_binary_hunk(h)]

    try:
        if text:
            patch = build_patch(text, diff_output)
            apply_patch(patch, cached=cached, reverse=reverse)
        if binary:
            binary_files = [h.file for h in binary]
            if reverse and not cached:
                discard_files(binary_files)
            elif reverse:
                unstage_files(binary_files)
            else:
                stage_files(binary_files)
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc

    print_applied(selected, verb=verb)


@click.group(cls=CliGroup, invoke_without_command=True, add_help_option=False)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.option("-V", "--version", "show_version", is_flag=True)
@click.pass_context
def cli(ctx: click.Context, show_help: bool, show_version: bool) -> None:
    if show_version:
        print_version(__version__)
        return
    if show_help or ctx.invoked_subcommand is None:
        print_help(HELP)


def _get_untracked_entries(files: list[str] | None = None) -> list[Hunk]:
    _require_git_repo()
    paths = get_untracked_files()
    if files:
        paths = [p for p in paths if p in files]
    return [
        Hunk(
            id="",
            file=p,
            header="",
            additions=0,
            deletions=0,
            context_before="",
            diff="",
            status="untracked",
        )
        for p in paths
    ]


@cli.command("list", add_help_option=False)
@click.option("--staged", is_flag=True)
@click.option("--unstaged", is_flag=True)
@click.option("--json", "force_json", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("files", nargs=-1)
def cmd_list(
    staged: bool,
    unstaged: bool,
    force_json: bool,
    show_help: bool,
    files: tuple[str, ...],
) -> None:
    if show_help:
        print_help(HELP_LIST)
        return

    file_list = list(files) if files else None

    if staged and unstaged:
        raise CliError("cannot use --staged and --unstaged together")

    if staged:
        hunks, _ = _get_hunks(staged=True, files=file_list)
    elif unstaged:
        hunks, _ = _get_hunks(staged=False, files=file_list)
    else:
        hunks_staged, _ = _get_hunks(staged=True, files=file_list)
        hunks_unstaged, _ = _get_hunks(staged=False, files=file_list)
        hunks = hunks_staged + hunks_unstaged + _get_untracked_entries(files=file_list)

    if force_json:
        click.echo(json.dumps([h.to_dict() for h in hunks], indent=2))
    else:
        print_hunk_list(hunks)


@cli.command("show", add_help_option=False)
@click.option("--staged", is_flag=True)
@click.option("--unstaged", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("ids", nargs=-1)
def cmd_show(
    staged: bool,
    unstaged: bool,
    show_help: bool,
    ids: tuple[str, ...],
) -> None:
    if show_help:
        print_help(HELP_SHOW)
        return

    if staged and unstaged:
        raise CliError("cannot use --staged and --unstaged together")

    if staged:
        hunks, _ = _get_hunks(staged=True)
    elif unstaged:
        hunks, _ = _get_hunks(staged=False)
    else:
        hunks_staged, _ = _get_hunks(staged=True)
        hunks_unstaged, _ = _get_hunks(staged=False)
        hunks = hunks_staged + hunks_unstaged

    if ids:
        matched = _find_hunks_by_ids(hunks, list(ids))
    else:
        matched = hunks

    print_hunk_diffs(matched)


@cli.command("stage", add_help_option=False)
@click.option("-l", "line_spec", default=None)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("ids", nargs=-1)
def cmd_stage(ids: tuple[str, ...], line_spec: str | None, show_help: bool) -> None:
    if show_help:
        print_help(HELP_STAGE)
        return
    _run_patch_command(
        list(ids),
        line_spec,
        usage=USAGE_STAGE,
        command_name="stage",
        staged=False,
        cached=True,
        reverse=False,
        verb="staged",
    )


@cli.command("unstage", add_help_option=False)
@click.option("-l", "line_spec", default=None)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("ids", nargs=-1)
def cmd_unstage(ids: tuple[str, ...], line_spec: str | None, show_help: bool) -> None:
    if show_help:
        print_help(HELP_UNSTAGE)
        return
    _run_patch_command(
        list(ids),
        line_spec,
        usage=USAGE_UNSTAGE,
        command_name="unstage",
        staged=True,
        cached=True,
        reverse=True,
        verb="unstaged",
    )


@cli.command("discard", add_help_option=False)
@click.option("-l", "line_spec", default=None)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("ids", nargs=-1)
def cmd_discard(ids: tuple[str, ...], line_spec: str | None, show_help: bool) -> None:
    if show_help:
        print_help(HELP_DISCARD)
        return
    _run_patch_command(
        list(ids),
        line_spec,
        usage=USAGE_DISCARD,
        command_name="discard",
        staged=False,
        cached=False,
        reverse=True,
        verb="discarded",
    )
