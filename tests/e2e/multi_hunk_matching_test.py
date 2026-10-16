import textwrap
from typing import Final

import pytest

from .conftest import GitHunkCLI


@pytest.fixture
def rename_and_fix(*, cli: GitHunkCLI) -> GitHunkCLI:
    # A Decimal switch spread over two hunks, and an unrelated tax fix in a
    # third hunk between them.
    BASE: Final = textwrap.dedent(
        """\
        def line_total(price, quantity):
            return float(price) * quantity


        # Rates follow the 2026 schedule.
        # Rounding happens at checkout.
        # Amounts are in the store currency.


        def tax(amount):
            return amount * 0.08


        # Totals include every line.
        # Discounts apply before tax.
        # Shipping is billed separately.


        def order_total(lines):
            total = 0
            for line in lines:
                total += line_total(line)
            return total
        """
    )
    cli.repo.write_file("orders.py", BASE)
    cli.repo.git("add", "orders.py")
    cli.repo.git("commit", "-m", "init")
    final = (
        BASE.replace("float(price)", "Decimal(price)")
        .replace("0.08", "0.1")
        .replace("total = 0", "total = Decimal(0)")
    )
    cli.repo.write_file("orders.py", final)
    assert len(cli.run_list_json("list", "--json")) == 3
    return cli


def test_include_matching_commits_matching_lines_across_hunks(
    *, rename_and_fix: GitHunkCLI
) -> None:
    cli = rename_and_fix

    cli.run_ok(
        "commit",
        "orders.py",
        "--include-matching",
        "price",
        "--include-matching",
        "total = ",
        "-m",
        "use Decimal",
    )

    committed = cli.repo.git("show", "HEAD:orders.py")
    assert "Decimal(price)" in committed
    assert "total = Decimal(0)" in committed
    assert "0.08" in committed
    remaining = cli.repo.git("diff")
    assert "-    return amount * 0.08" in remaining
    assert "Decimal" not in remaining


def test_exclude_matching_takes_hunks_without_a_match_whole(
    *, rename_and_fix: GitHunkCLI
) -> None:
    cli = rename_and_fix

    cli.run_ok(
        "commit", "orders.py", "--exclude-matching", "amount", "-m", "use Decimal"
    )

    committed = cli.repo.git("show", "HEAD:orders.py")
    assert "Decimal(price)" in committed
    assert "total = Decimal(0)" in committed
    assert "0.08" in committed


def test_ids_from_several_hunks_accept_content_matching(
    *, rename_and_fix: GitHunkCLI
) -> None:
    cli = rename_and_fix
    ids = [hunk["id"] for hunk in cli.run_list_json("list", "--json")]

    cli.run_ok(
        "stage",
        *ids,
        "--include-matching",
        "Decimal",
        "--include-matching",
        "float",
        "--include-matching",
        "= 0",
    )

    assert "0.08" in cli.repo.git("show", ":orders.py")
    assert "Decimal(0)" in cli.repo.git("show", ":orders.py")


def test_pattern_that_matches_no_hunk_is_an_error(
    *, rename_and_fix: GitHunkCLI
) -> None:
    cli = rename_and_fix

    result = cli.run("stage", "orders.py", "--include-matching", "nowhere")

    assert result.returncode == 1
    assert "no changed line matches 'nowhere'" in result.stderr
    assert cli.repo.git("diff", "--cached") == ""


def test_line_numbers_still_need_one_hunk(*, rename_and_fix: GitHunkCLI) -> None:
    cli = rename_and_fix

    result = cli.run("stage", "orders.py", "-l", "2")

    assert result.returncode == 1
    assert "-l requires exactly one hunk" in result.stderr


def test_hunk_whose_every_change_is_excluded_is_left_out(
    *, rename_and_fix: GitHunkCLI
) -> None:
    cli = rename_and_fix

    cli.run_ok(
        "commit",
        "orders.py",
        "--exclude-matching",
        "price",
        "--exclude-matching",
        "total = ",
        "-m",
        "raise tax",
    )

    committed = cli.repo.git("show", "HEAD:orders.py")
    assert "amount * 0.1" in committed
    assert "float(price)" in committed
    assert "total = 0" in committed


def test_line_exclusion_counts_context_lines(*, cli: GitHunkCLI) -> None:
    # Excluding one context line by position leaves as many excluded lines as
    # changed ones, which must not read as "every change excluded".
    cli.repo.write_file("f.txt", "a\nb\nc\n")
    cli.repo.git("add", "f.txt")
    cli.repo.git("commit", "-m", "init")
    cli.repo.write_file("f.txt", "a\nb\nc\nd\n")

    cli.run_ok("stage", cli.get_only_hunk_id("--unstaged"), "-l", "^1")

    assert cli.repo.git("show", ":f.txt") == "a\nb\nc\nd\n"
