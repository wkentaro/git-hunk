import json
import os
import posixpath
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace
from typing import Final

import click

from . import __version__
from ._git import GitCommandError
from ._git import apply_patch
from ._git import commit
from ._git import discard_files
from ._git import get_diff
from ._git import get_unmerged_files
from ._git import get_unsupported_changes
from ._git import get_untracked_files
from ._git import get_worktree_root
from ._git import stage_files
from ._git import unstage_added_files
from ._git import unstage_files
from ._hunk import Hunk
from ._hunk import assign_hunk_ids
from ._hunk import format_hunk_id
from ._hunk import is_submodule_hunk
from ._hunk import is_whole_file_hunk
from ._hunk import parse_diff
from ._hunk import whole_file_hunk
from ._lines import count_hunk_body_lines
from ._lines import filter_hunk_lines
from ._lines import parse_line_spec
from ._lines import resolve_matching_lines
from ._patch import build_patch
from ._skills import Skill
from ._skills import load_skills
from ._skills import skills_root
from ._ui import HELP
from ._ui import HELP_COMMIT
from ._ui import HELP_DISCARD
from ._ui import HELP_LIST
from ._ui import HELP_SHOW
from ._ui import HELP_SKILLS
from ._ui import HELP_STAGE
from ._ui import HELP_UNSTAGE
from ._ui import USAGE
from ._ui import USAGE_COMMIT
from ._ui import USAGE_DISCARD
from ._ui import USAGE_LIST
from ._ui import USAGE_SHOW
from ._ui import USAGE_SKILLS
from ._ui import USAGE_STAGE
from ._ui import USAGE_UNSTAGE
from ._ui import print_applied
from ._ui import print_committed
from ._ui import print_error
from ._ui import print_help
from ._ui import print_hunk_diffs
from ._ui import print_hunk_list
from ._ui import print_skill_list
from ._ui import print_version

# Bump when the `--json` shape changes incompatibly (see README JSON output).
JSON_SCHEMA_VERSION: Final = 2


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


def _require_worktree_root() -> str:
    try:
        return get_worktree_root()
    # Usually there is no worktree to anchor to, but rev-parse also refuses on
    # dubious ownership or a bad config value, and those say how to fix them.
    # Classifying git's English is what this avoids; passing it on is not.
    except GitCommandError as exc:
        raise CliError("not a git repository", tip=exc.stderr) from exc
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc


def _echo_json(data: object) -> None:
    click.echo(json.dumps(data, indent=2))


def _echo_hunks_json(hunks: list[Hunk], *, include_lines: bool = False) -> None:
    _echo_json(
        {
            "schema_version": JSON_SCHEMA_VERSION,
            "hunks": [h.to_dict(include_lines=include_lines) for h in hunks],
        }
    )


def _get_hunks(*, worktree_root: str, staged: bool) -> tuple[list[Hunk], str]:
    try:
        unmerged_files = get_unmerged_files(worktree_root=worktree_root)
        if unmerged_files:
            paths = ", ".join(repr(path) for path in unmerged_files)
            raise CliError(
                f"unmerged index entries are not supported: {paths}",
                tip="resolve the unmerged index with Git, then retry",
            )
        unsupported_changes = get_unsupported_changes(
            worktree_root=worktree_root, staged=staged
        )
        if unsupported_changes:
            details = "; ".join(
                f"{change.kind}: {change.source!r} -> {change.destination!r}"
                for change in unsupported_changes
            )
            raise CliError(
                f"unsupported file changes: {details}",
                tip="use Git directly for rename and copy changes",
            )
        diff_output = get_diff(worktree_root=worktree_root, staged=staged)
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc
    hunks = parse_diff(diff_output)
    status = "staged" if staged else "unstaged"
    hunks = [replace(h, status=status) for h in hunks]
    return hunks, diff_output


@dataclass(frozen=True)
class _Inventory:
    hunks: list[Hunk]
    staged_diff: str
    unstaged_diff: str


def _get_inventory(*, worktree_root: str) -> _Inventory:
    staged_hunks, staged_diff = _get_hunks(worktree_root=worktree_root, staged=True)
    unstaged_hunks, unstaged_diff = _get_hunks(
        worktree_root=worktree_root, staged=False
    )
    return _Inventory(
        hunks=assign_hunk_ids(staged_hunks + unstaged_hunks),
        staged_diff=staged_diff,
        unstaged_diff=unstaged_diff,
    )


def _find_hunks_by_ids(hunks: list[Hunk], ids: list[str]) -> list[Hunk]:
    def format_candidate(hunk: Hunk) -> str:
        marker = " (conditional)" if hunk.id_stability == "conditional" else ""
        return format_hunk_id(hunk) + marker

    found = []
    for hunk_id in ids:
        if not hunk_id.strip():
            raise CliError("hunk id must not be empty or whitespace")
        matches = [h for h in hunks if h.id.startswith(hunk_id.lower())]
        if len(matches) == 0:
            available = [format_candidate(h) for h in hunks]
            tip = f"available hunk ids: {', '.join(available)}" if available else None
            raise CliError(f"hunk '{hunk_id}' not found", tip=tip)
        if len(matches) > 1:
            candidates = ", ".join(format_candidate(m) for m in matches)
            raise CliError(
                f"ambiguous hunk id '{hunk_id}'",
                tip=f"matches: {candidates}",
            )
        found.append(matches[0])
    return found


def _make_repository_path(arg: str, *, worktree_root: str) -> str:
    tip = f"repository paths are relative to the worktree root ({worktree_root})"
    if not arg:
        raise CliError("repository path must not be empty", tip=tip)
    # git reports forward-slash paths on every platform, so translate the
    # OS-native separator and collapse ./ before comparing a CLI path argument
    # against them (os.path would rewrite separators the wrong way on Windows).
    drive, _ = os.path.splitdrive(arg)
    path = posixpath.normpath(arg.replace(os.sep, "/"))
    if drive or os.path.isabs(arg) or posixpath.isabs(path):
        raise CliError(f"repository path must be relative: '{arg}'", tip=tip)
    if path == ".." or path.startswith("../"):
        raise CliError(f"repository path escapes the worktree: '{arg}'", tip=tip)
    return path


@dataclass(frozen=True)
class _Target:
    # The argument as the user typed it, kept for the hex-id test and for
    # quoting the user's own spelling back in errors.
    arg: str
    path: str


def _make_targets(
    args: list[str], *, worktree_root: str, command_name: str, usage: str
) -> list[_Target]:
    if not args:
        raise CliError(
            f"{command_name} requires at least one hunk id or repository path",
            usage=usage,
        )
    return [
        _Target(
            arg=arg,
            path=_make_repository_path(arg, worktree_root=worktree_root),
        )
        for arg in args
    ]


def _select_hunks(
    hunks: list[Hunk], targets: list[_Target], *, inventory_hunks: list[Hunk]
) -> list[Hunk]:
    files = {h.file for h in hunks}
    eligible_ids = {hunk.id for hunk in hunks}
    selected: list[Hunk] = []
    seen: set[str] = set()
    for target in targets:
        # A path that matches a changed file wins; otherwise hunk ids are hex,
        # so a non-hex argument can only have been meant as a (missing) path.
        if target.path in files:
            matches = [h for h in hunks if h.file == target.path]
        elif re.fullmatch(r"[0-9a-fA-F]+", target.arg):
            matches = _find_hunks_by_ids(inventory_hunks, [target.arg])
            if matches[0].id not in eligible_ids:
                raise CliError(f"hunk '{target.arg}' is not eligible for this command")
        else:
            raise CliError(
                f"no changed file matches '{target.arg}'",
                tip="run 'git-hunk list' to see changed files and hunk ids",
            )
        for hunk in matches:
            if hunk.id not in seen:
                seen.add(hunk.id)
                selected.append(hunk)
    return selected


@dataclass(frozen=True)
class _Selection:
    line_spec: str | None
    include_matching: tuple[str, ...]
    exclude_matching: tuple[str, ...]
    regex: bool

    def is_active(self) -> bool:
        return (
            self.line_spec is not None
            or bool(self.include_matching)
            or bool(self.exclude_matching)
        )

    def resolve(self, hunk: Hunk) -> tuple[set[int], bool]:
        if self.line_spec is not None:
            return parse_line_spec(self.line_spec, total=count_hunk_body_lines(hunk))
        if self.include_matching:
            lines = resolve_matching_lines(
                hunk, self.include_matching, regex=self.regex
            )
            return lines, False
        lines = resolve_matching_lines(hunk, self.exclude_matching, regex=self.regex)
        return lines, True


def _build_selection(
    line_spec: str | None,
    include_matching: tuple[str, ...],
    exclude_matching: tuple[str, ...],
    regex: bool,
    *,
    usage: str,
) -> _Selection:
    mechanisms = [line_spec is not None, bool(include_matching), bool(exclude_matching)]
    if sum(mechanisms) > 1:
        raise CliError(
            "choose one of -l, --include-matching, or --exclude-matching",
            usage=usage,
        )
    if regex and not (include_matching or exclude_matching):
        raise CliError(
            "--regex requires --include-matching or --exclude-matching",
            usage=usage,
        )
    return _Selection(
        line_spec=line_spec,
        include_matching=include_matching,
        exclude_matching=exclude_matching,
        regex=regex,
    )


def _apply_line_filter(
    hunks: list[Hunk], selection: _Selection, *, reverse: bool
) -> list[Hunk]:
    if not selection.is_active():
        return hunks
    if len(hunks) != 1:
        raise CliError("line selection requires exactly one hunk")
    if is_whole_file_hunk(hunks[0]):
        raise CliError(
            "line selection is not supported for binary, mode, or type changes, "
            "or empty files"
        )
    if is_submodule_hunk(hunks[0]):
        raise CliError(
            "line selection is not supported for submodule changes",
            tip="select the hunk as a whole",
        )
    try:
        lines, exclude = selection.resolve(hunks[0])
        return [filter_hunk_lines(hunks[0], lines, exclude=exclude, reverse=reverse)]
    except ValueError as exc:
        raise CliError(str(exc)) from exc


def _apply_selection(
    targets: list[_Target],
    selection: _Selection,
    *,
    worktree_root: str,
    staged: bool,
    cached: bool,
    reverse: bool,
    dry_run: bool,
    inventory: _Inventory | None = None,
) -> list[Hunk]:
    inventory = inventory or _get_inventory(worktree_root=worktree_root)
    status = "staged" if staged else "unstaged"
    hunks = [hunk for hunk in inventory.hunks if hunk.status == status]
    diff_output = inventory.staged_diff if staged else inventory.unstaged_diff
    selected = _select_hunks(hunks, targets, inventory_hunks=inventory.hunks)
    selected = _apply_line_filter(selected, selection, reverse=reverse)

    patch_hunks = [
        hunk for hunk in selected if not hunk.binary and hunk.change_kind != "T"
    ]
    file_command_hunks = [
        hunk for hunk in selected if hunk.binary or hunk.change_kind == "T"
    ]

    try:
        patch = (
            build_patch(patch_hunks, diff_output, reverse=reverse)
            if patch_hunks
            else None
        )
        if patch is not None:
            apply_patch(
                patch,
                worktree_root=worktree_root,
                cached=cached,
                reverse=reverse,
                dry_run=True,
            )
        file_command_files = [hunk.file for hunk in file_command_hunks]
        added_file_command_files = [
            hunk.file for hunk in file_command_hunks if hunk.change_kind == "A"
        ]
        tracked_file_command_files = [
            hunk.file for hunk in file_command_hunks if hunk.change_kind != "A"
        ]
        if file_command_files and not reverse:
            stage_files(
                file_command_files,
                worktree_root=worktree_root,
                dry_run=True,
            )
        if added_file_command_files and reverse and cached:
            unstage_added_files(
                added_file_command_files,
                worktree_root=worktree_root,
                dry_run=True,
            )
        if dry_run:
            return selected

        if patch is not None:
            apply_patch(
                patch,
                worktree_root=worktree_root,
                cached=cached,
                reverse=reverse,
                dry_run=False,
            )
        if file_command_files:
            if reverse and not cached:
                discard_files(file_command_files, worktree_root=worktree_root)
            elif reverse:
                if added_file_command_files:
                    unstage_added_files(
                        added_file_command_files,
                        worktree_root=worktree_root,
                        dry_run=False,
                    )
                if tracked_file_command_files:
                    unstage_files(
                        tracked_file_command_files,
                        worktree_root=worktree_root,
                    )
            else:
                stage_files(
                    file_command_files,
                    worktree_root=worktree_root,
                    dry_run=False,
                )
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc

    return selected


def _run_patch_command(
    args: list[str],
    selection: _Selection,
    *,
    usage: str,
    command_name: str,
    staged: bool,
    cached: bool,
    reverse: bool,
    verb: str,
    dry_run: bool,
) -> None:
    worktree_root = _require_worktree_root()
    targets = _make_targets(
        args,
        worktree_root=worktree_root,
        command_name=command_name,
        usage=usage,
    )
    selected = _apply_selection(
        targets,
        selection,
        worktree_root=worktree_root,
        staged=staged,
        cached=cached,
        reverse=reverse,
        dry_run=dry_run,
    )
    print_applied(selected, verb=f"would {command_name}" if dry_run else verb)


@click.group(cls=CliGroup, invoke_without_command=True, add_help_option=False)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.option("-V", "--version", "show_version", is_flag=True)
@click.pass_context
def cli(ctx: click.Context, show_help: bool, show_version: bool) -> None:
    if show_version:
        print_version(__version__)
        ctx.exit()
    if show_help or ctx.invoked_subcommand is None:
        print_help(HELP)
        ctx.exit()


def _working_tree_mode(path: str) -> str:
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        return "120000"
    return "100755" if mode & 0o100 else "100644"


def _get_untracked_entries(*, worktree_root: str) -> list[Hunk]:
    paths = get_untracked_files(worktree_root=worktree_root)
    if not paths:
        return []
    return [
        whole_file_hunk(
            p,
            change_kind="A",
            a_mode=None,
            b_mode=_working_tree_mode(posixpath.join(worktree_root, p)),
            binary=False,
            a_object_id=None,
            b_object_id=None,
            status="untracked",
        )
        for p in paths
    ]


def _filter_inventory_hunks(
    inventory: _Inventory,
    *,
    worktree_root: str,
    staged: bool,
    unstaged: bool,
    include_untracked: bool,
    usage: str,
) -> list[Hunk]:
    if staged and unstaged:
        raise CliError("cannot use --staged and --unstaged together", usage=usage)

    if staged or unstaged:
        status = "staged" if staged else "unstaged"
        return [hunk for hunk in inventory.hunks if hunk.status == status]
    hunks = inventory.hunks[:]
    if include_untracked:
        hunks += _get_untracked_entries(worktree_root=worktree_root)
    return hunks


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

    worktree_root = _require_worktree_root()
    selected_paths = {
        _make_repository_path(path, worktree_root=worktree_root) for path in files
    }

    inventory = _get_inventory(worktree_root=worktree_root)
    hunks = _filter_inventory_hunks(
        inventory,
        worktree_root=worktree_root,
        staged=staged,
        unstaged=unstaged,
        include_untracked=True,
        usage=USAGE_LIST,
    )
    if selected_paths:
        hunks = [hunk for hunk in hunks if hunk.file in selected_paths]

    if force_json:
        _echo_hunks_json(hunks)
    else:
        print_hunk_list(hunks)


@cli.command("show", add_help_option=False)
@click.option("--staged", is_flag=True)
@click.option("--unstaged", is_flag=True)
@click.option("--json", "force_json", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("ids", nargs=-1)
def cmd_show(
    staged: bool,
    unstaged: bool,
    force_json: bool,
    show_help: bool,
    ids: tuple[str, ...],
) -> None:
    if show_help:
        print_help(HELP_SHOW)
        return

    worktree_root = _require_worktree_root()
    inventory = _get_inventory(worktree_root=worktree_root)
    hunks = _filter_inventory_hunks(
        inventory,
        worktree_root=worktree_root,
        staged=staged,
        unstaged=unstaged,
        include_untracked=False,
        usage=USAGE_SHOW,
    )

    if ids:
        matched = _find_hunks_by_ids(inventory.hunks, list(ids))
        visible_ids = {hunk.id for hunk in hunks}
        if any(hunk.id not in visible_ids for hunk in matched):
            raise CliError("requested hunk is outside the selected status")
    else:
        matched = hunks

    if force_json:
        _echo_hunks_json(matched, include_lines=True)
    else:
        print_hunk_diffs(matched)


def _find_skill(skills: list[Skill], name: str) -> Skill:
    for skill in skills:
        if skill.name == name:
            return skill
    available = ", ".join(skill.name for skill in skills)
    raise CliError(
        f"skill '{name}' not found",
        tip=f"available skills: {available}" if available else None,
    )


@cli.command("skills", add_help_option=False)
@click.option("--json", "force_json", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("args", nargs=-1)
def cmd_skills(args: tuple[str, ...], force_json: bool, show_help: bool) -> None:
    if show_help:
        print_help(HELP_SKILLS)
        return

    subcommand = args[0] if args else "list"
    rest = args[1:]

    if subcommand == "list":
        if rest:
            raise CliError("skills list takes no arguments", usage=USAGE_SKILLS)
        skills = load_skills()
        if force_json:
            data = [{"name": s.name, "description": s.description} for s in skills]
            _echo_json(data)
        else:
            print_skill_list(skills)
        return

    if subcommand == "get":
        if not rest:
            raise CliError("skills get requires a skill name", usage=USAGE_SKILLS)
        skills = load_skills()
        selected = [_find_skill(skills, name) for name in rest]
        if force_json:
            data = [{"name": s.name, "content": s.content} for s in selected]
            _echo_json(data)
        else:
            click.echo("\n".join(s.content.rstrip("\n") for s in selected))
        return

    if subcommand == "path":
        if len(rest) > 1:
            raise CliError(
                "skills path takes at most one skill name", usage=USAGE_SKILLS
            )
        path = _find_skill(load_skills(), rest[0]).path if rest else skills_root()
        if force_json:
            _echo_json({"path": str(path)})
        else:
            click.echo(str(path))
        return

    raise CliError(f"unrecognized skills subcommand '{subcommand}'", usage=USAGE_SKILLS)


def _add_patch_selection_options(command: Callable[..., None]) -> Callable[..., None]:
    options = [
        click.option("-l", "line_spec", default=None),
        click.option("--include-matching", "include_matching", multiple=True),
        click.option("--exclude-matching", "exclude_matching", multiple=True),
        click.option("--regex", "use_regex", is_flag=True),
        click.option("--dry-run", "dry_run", is_flag=True),
        click.option("-h", "--help", "show_help", is_flag=True),
        click.argument("targets", nargs=-1),
    ]
    for option in reversed(options):
        command = option(command)
    return command


@cli.command("stage", add_help_option=False)
@_add_patch_selection_options
def cmd_stage(
    targets: tuple[str, ...],
    line_spec: str | None,
    include_matching: tuple[str, ...],
    exclude_matching: tuple[str, ...],
    use_regex: bool,
    dry_run: bool,
    show_help: bool,
) -> None:
    if show_help:
        print_help(HELP_STAGE)
        return
    selection = _build_selection(
        line_spec, include_matching, exclude_matching, use_regex, usage=USAGE_STAGE
    )
    _run_patch_command(
        list(targets),
        selection,
        usage=USAGE_STAGE,
        command_name="stage",
        staged=False,
        cached=True,
        reverse=False,
        verb="staged",
        dry_run=dry_run,
    )


@cli.command("unstage", add_help_option=False)
@_add_patch_selection_options
def cmd_unstage(
    targets: tuple[str, ...],
    line_spec: str | None,
    include_matching: tuple[str, ...],
    exclude_matching: tuple[str, ...],
    use_regex: bool,
    dry_run: bool,
    show_help: bool,
) -> None:
    if show_help:
        print_help(HELP_UNSTAGE)
        return
    selection = _build_selection(
        line_spec, include_matching, exclude_matching, use_regex, usage=USAGE_UNSTAGE
    )
    _run_patch_command(
        list(targets),
        selection,
        usage=USAGE_UNSTAGE,
        command_name="unstage",
        staged=True,
        cached=True,
        reverse=True,
        verb="unstaged",
        dry_run=dry_run,
    )


@cli.command("discard", add_help_option=False)
@_add_patch_selection_options
def cmd_discard(
    targets: tuple[str, ...],
    line_spec: str | None,
    include_matching: tuple[str, ...],
    exclude_matching: tuple[str, ...],
    use_regex: bool,
    dry_run: bool,
    show_help: bool,
) -> None:
    if show_help:
        print_help(HELP_DISCARD)
        return
    selection = _build_selection(
        line_spec, include_matching, exclude_matching, use_regex, usage=USAGE_DISCARD
    )
    _run_patch_command(
        list(targets),
        selection,
        usage=USAGE_DISCARD,
        command_name="discard",
        staged=False,
        cached=False,
        reverse=True,
        verb="discarded",
        dry_run=dry_run,
    )


@cli.command("commit", add_help_option=False)
@click.option("-m", "message", default=None)
@click.option("-l", "line_spec", default=None)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("targets", nargs=-1)
def cmd_commit(
    targets: tuple[str, ...],
    message: str | None,
    line_spec: str | None,
    show_help: bool,
) -> None:
    if show_help:
        print_help(HELP_COMMIT)
        return
    if message is None or not message.strip():
        raise CliError("commit requires a message (-m)", usage=USAGE_COMMIT)

    worktree_root = _require_worktree_root()
    commit_targets = _make_targets(
        list(targets),
        worktree_root=worktree_root,
        command_name="commit",
        usage=USAGE_COMMIT,
    )
    inventory = _get_inventory(worktree_root=worktree_root)
    if inventory.staged_diff.strip():
        raise CliError(
            "cannot commit: changes are already staged",
            tip="commit them with 'git commit', or unstage with 'git-hunk unstage'",
        )

    selection = _Selection(
        line_spec=line_spec, include_matching=(), exclude_matching=(), regex=False
    )
    selected = _apply_selection(
        commit_targets,
        selection,
        worktree_root=worktree_root,
        staged=False,
        cached=True,
        reverse=False,
        dry_run=False,
        inventory=inventory,
    )
    try:
        commit(message, worktree_root=worktree_root)
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc

    print_committed(selected, message=message)
