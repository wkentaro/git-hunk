import pytest

from .conftest import MutationRepoFactory
from .conftest import get_target
from .conftest import snapshot_repository


@pytest.mark.parametrize("command", ["stage", "unstage", "discard"])
@pytest.mark.parametrize("selection", ["file", "id"])
@pytest.mark.parametrize(
    ("kind", "path", "before", "after"),
    [
        ("text", "sibling/change.txt", b"text old\n", b"text new\n"),
        ("binary", "sibling/change.bin", b"\x00old\xff", b"\x00new\xfe"),
    ],
)
def test_dry_run_keeps_complete_repository_state(
    make_mutation_repo: MutationRepoFactory,
    command: str,
    selection: str,
    kind: str,
    path: str,
    before: bytes,
    after: bytes,
) -> None:
    cli = make_mutation_repo(path, before, after)
    staged = command == "unstage"
    if staged:
        cli.repo.git("add", path)
    target = get_target(cli, path=path, selection=selection, staged=staged)
    state_before = snapshot_repository(cli)

    result = cli.run(command, target, "--dry-run", subdir="sub")

    assert result.returncode == 0, f"{kind}: {result.stderr}"
    assert path in result.stderr
    assert snapshot_repository(cli) == state_before
