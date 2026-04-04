import json
import sys

import click

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
from .ui import print_applied
from .ui import print_error
from .ui import print_help
from .ui import print_hunk_diff
from .ui import print_hunk_list
from .ui import print_version


class CliError(Exception):
    def __init__(
        self,
        message: str,
        *,
        tip: str | None = None,
        help_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tip = tip
        self.help_text = help_text


class CliGroup(click.Group):
    def invoke(self, ctx: click.Context) -> None:
        try:
            super().invoke(ctx)
        except CliError as exc:
            print_error(str(exc), tip=exc.tip)
            if exc.help_text:
                print_help(exc.help_text)
            ctx.exit(1)
        except KeyboardInterrupt:
            ctx.exit(130)


def _get_hunks(staged: bool, files: list[str] | None = None) -> list[Hunk]:
    return parse_diff(get_diff(staged=staged, files=files))


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


def _run_patch_command(
    ids: list[str],
    line_spec: str | None,
    *,
    help_text: str,
    command_name: str,
    staged: bool,
    cached: bool,
    reverse: bool,
    verb: str,
) -> None:
    if not ids:
        raise CliError(
            f"{command_name} requires at least one hunk id",
            help_text=help_text,
        )

    hunks = _get_hunks(staged=staged)
    selected = _find_hunks_by_ids(hunks, ids)
    selected = _apply_line_filter(selected, line_spec)
    diff_output = get_diff(staged=staged)
    patch = build_patch(selected, diff_output)

    try:
        apply_patch(patch, cached=cached, reverse=reverse)
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc

    print_applied(selected, verb=verb)


@click.group(cls=CliGroup, invoke_without_command=True, add_help_option=False)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.option("-V", "--version", "show_version", is_flag=True)
@click.pass_context
def cli(ctx: click.Context, show_help: bool, show_version: bool) -> None:
    if show_version:
        from . import __version__

        print_version(__version__)
        return
    if show_help or ctx.invoked_subcommand is None:
        print_help(HELP)


@cli.command("list", add_help_option=False)
@click.option("--staged", is_flag=True)
@click.option("--json", "force_json", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("files", nargs=-1)
def cmd_list(
    staged: bool, force_json: bool, show_help: bool, files: tuple[str, ...]
) -> None:
    if show_help:
        print_help(HELP_LIST)
        return

    hunks = _get_hunks(staged=staged, files=list(files) if files else None)

    if force_json or not sys.stdout.isatty():
        click.echo(json.dumps([h.to_dict() for h in hunks], indent=2))
    else:
        print_hunk_list(hunks)


@cli.command("show", add_help_option=False)
@click.option("--staged", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("hunk_id", required=False)
def cmd_show(staged: bool, show_help: bool, hunk_id: str | None) -> None:
    if show_help:
        print_help(HELP_SHOW)
        return

    if not hunk_id:
        raise CliError("show requires a hunk id", help_text=HELP_SHOW)

    hunks = _get_hunks(staged=staged)
    (hunk,) = _find_hunks_by_ids(hunks, [hunk_id])

    if sys.stdout.isatty():
        print_hunk_diff(hunk)
    else:
        lines = hunk.diff.split("\n")
        line_num = 0
        for line in lines:
            if line.startswith("@@"):
                click.echo(line)
            else:
                line_num += 1
                click.echo(f"{line_num}: {line}")


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
        help_text=HELP_STAGE,
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
        help_text=HELP_UNSTAGE,
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
        help_text=HELP_DISCARD,
        command_name="discard",
        staged=False,
        cached=False,
        reverse=True,
        verb="discarded",
    )
