"""Materialize the file content a stage selection would produce.

The real index and working tree stay untouched: the selected patch is applied
to a throwaway copy of the index (see `_git.scratch_index`) and the resulting
blob is read back from that copy. Applying the patch does write the resulting
blob into the repository's object database, where it stays unreferenced until
`git gc` reclaims it.

`materialize_staged_content` is the whole seam, guards included, so a caller
gets the rejections rather than an opaque `git apply` failure.
"""

from ._git import GitCommandError
from ._git import apply_patch
from ._git import read_index_blob
from ._git import scratch_index
from ._hunk import Hunk
from ._hunk import is_submodule_hunk
from ._hunk import is_whole_file_hunk
from ._patch import build_patch


class StagedContentError(ValueError):
    """A selection with no materializable content, with a user-facing tip."""

    def __init__(self, message: str, *, tip: str | None = None) -> None:
        super().__init__(message)
        self.tip = tip


_NO_TEXT_TIP = "there is no text content to materialize"


def _check_materializable(hunks: list[Hunk]) -> str:
    files = {hunk.file for hunk in hunks}
    if len(files) != 1:
        raise StagedContentError(
            "staged content requires hunks from exactly one file",
            tip="one file's content is materialized at a time",
        )
    if any(hunk.binary or hunk.change_kind == "T" for hunk in hunks):
        raise StagedContentError(
            "staged content is not available for binary or type changes",
            tip=_NO_TEXT_TIP,
        )
    if any(is_submodule_hunk(hunk) for hunk in hunks):
        raise StagedContentError(
            "staged content is not available for submodule changes", tip=_NO_TEXT_TIP
        )
    if all(is_whole_file_hunk(hunk) for hunk in hunks):
        raise StagedContentError(
            "staged content is not available for mode-only changes or empty "
            "tracked file additions and deletions",
            tip=_NO_TEXT_TIP,
        )
    return files.pop()


def materialize_staged_content(
    hunks: list[Hunk], diff_output: str, *, worktree_root: str
) -> bytes:
    """Return the bytes staging `hunks` would leave in the index.

    `hunks` is a resolved selection (already line-filtered); `diff_output` is
    the unstaged diff it came from. Raises StagedContentError when the
    selection has no content to materialize or its patch does not apply.
    """
    filepath = _check_materializable(hunks)
    patch = build_patch(hunks, diff_output, reverse=False)
    with scratch_index(worktree_root=worktree_root) as env:
        try:
            apply_patch(
                patch,
                worktree_root=worktree_root,
                cached=True,
                reverse=False,
                dry_run=False,
                env=env,
            )
        # The scratch index is an implementation detail, so git's "apply
        # --cached" wording would point at an index this never writes. Its
        # stderr still says what was wrong with the patch, so keep it.
        except GitCommandError as exc:
            raise StagedContentError(
                f"cannot build the staged content for '{filepath}'", tip=exc.stderr
            ) from exc
        content = read_index_blob(filepath, worktree_root=worktree_root, env=env)
    if content is None:
        raise StagedContentError(
            f"the selection removes '{filepath}' from the index",
            tip="staging it leaves no file, so there is no content to emit",
        )
    return content
