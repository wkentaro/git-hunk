import json
import os
import posixpath
import re
import stat
from dataclasses import dataclass
from dataclasses import replace
from typing import Final

import click

from . import __version__
from ._git import apply_patch
from ._git import commit
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


def _require_git_repo() -> None:
    if not is_git_repo():
        raise CliError("not a git repository")


def _echo_json(data: object) -> None:
    click.echo(json.dumps(data, indent=2))


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
        if not hunk_id.strip():
            raise CliError("hunk id must not be empty or whitespace")
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


def _normalize_path_arg(arg: str) -> str:
    # git reports forward-slash paths on every platform, so translate the
    # OS-native separator and collapse ./ before comparing a CLI path argument
    # against them (os.path would rewrite separators the wrong way on Windows).
    return posixpath.normpath(arg.replace(os.sep, "/"))


def _select_hunks(hunks: list[Hunk], args: list[str]) -> list[Hunk]:
    files = {h.file for h in hunks}
    selected: list[Hunk] = []
    seen: set[str] = set()
    for arg in args:
        if not arg.strip():
            raise CliError("hunk id or file path must not be empty or whitespace")
        # A path that matches a changed file wins; otherwise hunk ids are hex,
        # so a non-hex argument can only have been meant as a (missing) path.
        path = _normalize_path_arg(arg)
        if path in files:
            matches = [h for h in hunks if h.file == path]
        elif re.fullmatch(r"[0-9a-f]+", arg):
            matches = _find_hunks_by_ids(hunks, [arg])
        else:
            raise CliError(
                f"no changed file matches '{arg}'",
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
            return parse_line_spec(self.line_spec)
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
    if _is_whole_file_hunk(hunks[0]):
        raise CliError(
            "line selection is not supported for binary, mode, or type changes"
        )
    try:
        lines, exclude = selection.resolve(hunks[0])
        return [filter_hunk_lines(hunks[0], lines, exclude=exclude, reverse=reverse)]
    except ValueError as exc:
        raise CliError(str(exc)) from exc


def _is_whole_file_hunk(hunk: Hunk) -> bool:
    # Binary and mode-only changes carry no text diff and are applied by staging
    # the whole file rather than by a patch.
    return not hunk.diff


def _apply_selection(
    args: list[str],
    selection: _Selection,
    *,
    usage: str,
    command_name: str,
    staged: bool,
    cached: bool,
    reverse: bool,
    dry_run: bool,
) -> list[Hunk]:
    if not args:
        raise CliError(
            f"{command_name} requires at least one hunk id or file path",
            usage=usage,
        )

    hunks, diff_output = _get_hunks(staged=staged)
    selected = _select_hunks(hunks, args)
    selected = _apply_line_filter(selected, selection, reverse=reverse)

    whole_file = [h for h in selected if _is_whole_file_hunk(h)]
    text = [h for h in selected if not _is_whole_file_hunk(h)]

    try:
        if text:
            patch = build_patch(text, diff_output)
            apply_patch(patch, cached=cached, reverse=reverse, dry_run=dry_run)
        if whole_file and not dry_run:
            paths = [h.file for h in whole_file]
            if reverse and not cached:
                discard_files(paths)
            elif reverse:
                unstage_files(paths)
            else:
                stage_files(paths)
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
    selected = _apply_selection(
        args,
        selection,
        usage=usage,
        command_name=command_name,
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
        return
    if show_help or ctx.invoked_subcommand is None:
        print_help(HELP)


def _working_tree_mode(path: str) -> str:
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        return "120000"
    return "100755" if mode & 0o100 else "100644"


def _get_untracked_entries(files: list[str] | None = None) -> list[Hunk]:
    _require_git_repo()
    paths = get_untracked_files()
    if files:
        wanted = {_normalize_path_arg(f) for f in files}
        paths = [p for p in paths if p in wanted]
    return [
        Hunk(
            id="",
            file=p,
            change_kind="A",
            a_mode=None,
            b_mode=_working_tree_mode(p),
            binary=False,
            header=None,
            context_before=None,
            additions=0,
            deletions=0,
            diff="",
            status="untracked",
        )
        for p in paths
    ]


def _collect_hunks(
    *,
    staged: bool,
    unstaged: bool,
    files: list[str] | None,
    include_untracked: bool,
) -> list[Hunk]:
    if staged and unstaged:
        raise CliError("cannot use --staged and --unstaged together")

    if staged:
        hunks, _ = _get_hunks(staged=True, files=files)
        return hunks
    if unstaged:
        hunks, _ = _get_hunks(staged=False, files=files)
        return hunks

    hunks_staged, _ = _get_hunks(staged=True, files=files)
    hunks_unstaged, _ = _get_hunks(staged=False, files=files)
    hunks = hunks_staged + hunks_unstaged
    if include_untracked:
        hunks += _get_untracked_entries(files=files)
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

    file_list = list(files) if files else None

    hunks = _collect_hunks(
        staged=staged,
        unstaged=unstaged,
        files=file_list,
        include_untracked=True,
    )

    if force_json:
        envelope = {
            "schema_version": JSON_SCHEMA_VERSION,
            "hunks": [h.to_dict() for h in hunks],
        }
        _echo_json(envelope)
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

    hunks = _collect_hunks(
        staged=staged,
        unstaged=unstaged,
        files=None,
        include_untracked=False,
    )

    if ids:
        matched = _find_hunks_by_ids(hunks, list(ids))
    else:
        matched = hunks

    if force_json:
        envelope = {
            "schema_version": JSON_SCHEMA_VERSION,
            "hunks": [h.to_dict(include_lines=True) for h in matched],
        }
        _echo_json(envelope)
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


@cli.command("stage", add_help_option=False)
@click.option("-l", "line_spec", default=None)
@click.option("--include-matching", "include_matching", multiple=True)
@click.option("--exclude-matching", "exclude_matching", multiple=True)
@click.option("--regex", "use_regex", is_flag=True)
@click.option("--dry-run", "dry_run", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("targets", nargs=-1)
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
@click.option("-l", "line_spec", default=None)
@click.option("--include-matching", "include_matching", multiple=True)
@click.option("--exclude-matching", "exclude_matching", multiple=True)
@click.option("--regex", "use_regex", is_flag=True)
@click.option("--dry-run", "dry_run", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("targets", nargs=-1)
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
@click.option("-l", "line_spec", default=None)
@click.option("--include-matching", "include_matching", multiple=True)
@click.option("--exclude-matching", "exclude_matching", multiple=True)
@click.option("--regex", "use_regex", is_flag=True)
@click.option("--dry-run", "dry_run", is_flag=True)
@click.option("-h", "--help", "show_help", is_flag=True)
@click.argument("targets", nargs=-1)
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

    _require_git_repo()
    try:
        already_staged = get_diff(staged=True).strip()
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc
    if already_staged:
        raise CliError(
            "cannot commit: changes are already staged",
            tip="commit them with 'git commit', or unstage with 'git-hunk unstage'",
        )

    selection = _Selection(
        line_spec=line_spec, include_matching=(), exclude_matching=(), regex=False
    )
    selected = _apply_selection(
        list(targets),
        selection,
        usage=USAGE_COMMIT,
        command_name="commit",
        staged=False,
        cached=True,
        reverse=False,
        dry_run=False,
    )
    try:
        commit(message)
    except RuntimeError as exc:
        raise CliError(str(exc)) from exc

    print_committed(selected, message=message)
