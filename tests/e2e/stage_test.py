from .conftest import GitHunkCLI


def test_stage_single_hunk(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_json("list", "--json")
    assert len(hunks) == 2

    cli.run_ok("stage", hunks[0]["id"])

    staged = cli.repo.git("diff", "--cached")
    assert "CHANGED2" in staged
    assert "CHANGED18" not in staged

    unstaged = cli.repo.git("diff")
    assert "CHANGED18" in unstaged


def test_stage_multiple_hunks(cli: GitHunkCLI) -> None:
    lines = [f"line{i}" for i in range(1, 21)]
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    lines[1] = "CHANGED2"
    lines[17] = "CHANGED18"
    cli.repo.write_file("f.py", "\n".join(lines) + "\n")

    hunks = cli.run_json("list", "--json")
    cli.run_ok("stage", hunks[0]["id"], hunks[1]["id"])

    staged = cli.repo.git("diff", "--cached")
    assert "CHANGED2" in staged
    assert "CHANGED18" in staged

    unstaged = cli.repo.git("diff")
    assert unstaged.strip() == ""


def test_stage_from_different_files(cli: GitHunkCLI) -> None:
    cli.repo.write_file("a.py", "aaa\n")
    cli.repo.write_file("b.py", "bbb\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")

    cli.repo.write_file("a.py", "AAA\n")
    cli.repo.write_file("b.py", "BBB\n")

    hunks = cli.run_json("list", "--json")
    a_hunk = next(h for h in hunks if h["file"] == "a.py")

    cli.run_ok("stage", a_hunk["id"])

    staged = cli.repo.git("diff", "--cached")
    assert "AAA" in staged
    assert "BBB" not in staged


def test_stage_with_line_include(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "line1\nline2\nline3\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "LINE1\nLINE2\nLINE3\n")

    hunks = cli.run_json("list", "--json")
    assert len(hunks) == 1

    # Diff body: 1=-line1, 2=-line2, 3=-line3, 4=+LINE1, 5=+LINE2, 6=+LINE3
    # Select lines 1,4 → stages line1→LINE1 only
    cli.run_ok("stage", hunks[0]["id"], "-l", "1,4")

    staged = cli.repo.git("diff", "--cached")
    assert "LINE1" in staged
    assert "LINE2" not in staged

    unstaged = cli.repo.git("diff")
    assert "LINE2" in unstaged
    assert "LINE3" in unstaged


def test_stage_with_line_exclude(cli: GitHunkCLI) -> None:
    cli.repo.write_file("f.py", "line1\nline2\nline3\n")
    cli.repo.git("add", ".")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.py", "LINE1\nLINE2\nLINE3\n")

    hunks = cli.run_json("list", "--json")
    assert len(hunks) == 1

    # Diff body: 1=-line1, 2=-line2, 3=-line3, 4=+LINE1, 5=+LINE2, 6=+LINE3
    # Exclude lines 3,6 → stages line1→LINE1 + line2→LINE2, keeps line3→LINE3 unstaged
    cli.run_ok("stage", hunks[0]["id"], "-l", "^3,^6")

    staged = cli.repo.git("diff", "--cached")
    assert "LINE1" in staged
    assert "LINE2" in staged
    assert "LINE3" not in staged
