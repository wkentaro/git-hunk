from pathlib import Path
from typing import get_args

from eval.grader import FailureReason
from eval.grader import Result
from eval.model import VARIANTS
from eval.model import TaskRun
from eval.model import TokenUsage
from eval.model import TraceUsage
from eval.scenario import Scenario
from eval.summary import REASON_LEGEND
from eval.summary import render_summary
from eval.tasks import SCENARIOS

_CACHE_CAVEAT = (
    "bare-git runs second and may read cache written by the git-hunk run; "
    "costs are not order-neutral."
)
_REPEAT_CAVEAT = (
    "Only the first repeat starts cold, so a cost range mixes cache warmup with "
    "run-to-run noise."
)


def _make_usage(*, turns: int, cost_usd: float) -> TraceUsage:
    return TraceUsage(
        duration_seconds=22.67,
        api_duration_seconds=22.62,
        turns=turns,
        tool_calls=turns - 1,
        cost_usd=cost_usd,
        tokens=TokenUsage(
            input_tokens=16,
            cache_creation_input_tokens=8434,
            cache_read_input_tokens=59782,
            output_tokens=1327,
        ),
        models={},
    )


def _make_run(
    *,
    scenario: Scenario,
    variant_index: int,
    passed: bool,
    reason: FailureReason | None = None,
    usage: TraceUsage | None,
    repeat: int = 1,
) -> TaskRun:
    return TaskRun(
        scenario=scenario,
        variant=VARIANTS[variant_index],
        result=Result(
            passed=passed, reason=reason, detail="detail" if reason else None
        ),
        trace_path=Path("trace.jsonl"),
        transcript_path=Path("transcript.txt"),
        usage=usage,
        repeat=repeat,
    )


def _make_repeats(
    *,
    scenario: Scenario,
    variant_index: int,
    samples: list[tuple[bool, FailureReason | None, int, float]],
) -> list[TaskRun]:
    return [
        _make_run(
            scenario=scenario,
            variant_index=variant_index,
            passed=passed,
            reason=reason,
            usage=_make_usage(turns=turns, cost_usd=cost_usd),
            repeat=repeat,
        )
        for repeat, (passed, reason, turns, cost_usd) in enumerate(samples, start=1)
    ]


def test_render_summary_pairs_variants_and_totals_reported_metrics() -> None:
    runs = [
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=0,
            passed=True,
            usage=_make_usage(turns=12, cost_usd=0.21),
        ),
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=1,
            passed=False,
            reason="order",
            usage=_make_usage(turns=9, cost_usd=0.18),
        ),
        _make_run(
            scenario=SCENARIOS[1],
            variant_index=0,
            passed=True,
            usage=_make_usage(turns=10, cost_usd=0.19),
        ),
        _make_run(
            scenario=SCENARIOS[1],
            variant_index=1,
            passed=False,
            reason="leftover-worktree",
            usage=_make_usage(turns=8, cost_usd=0.15),
        ),
    ]

    assert render_summary(runs=runs).splitlines() == [
        "| Task                      | git-hunk                    "
        "| bare-git                                 |",
        "| ------------------------- | --------------------------- "
        "| ---------------------------------------- |",
        "| split_refactor_vs_feature | PASS · 11c · 12t · $0.21    "
        "| FAIL order · 8c · 9t · $0.18             |",
        "| separate_mixed_hunks      | PASS · 9c · 10t · $0.19     "
        "| FAIL leftover-worktree · 7c · 8t · $0.15 |",
        "| **total**                 | **2/2 · 20c · 22t · $0.40** "
        "| **0/2 · 15c · 17t · $0.33**              |",
        "",
        _CACHE_CAVEAT,
        "",
        f"- order: {REASON_LEGEND['order']}",
        f"- leftover-worktree: {REASON_LEGEND['leftover-worktree']}",
    ]


def test_render_summary_omits_total_row_for_a_single_task() -> None:
    runs = [
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=0,
            passed=True,
            usage=_make_usage(turns=12, cost_usd=0.21),
        ),
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=1,
            passed=True,
            usage=_make_usage(turns=9, cost_usd=0.18),
        ),
    ]

    lines = render_summary(runs=runs).splitlines()

    assert lines == [
        "| Task                      | git-hunk                 "
        "| bare-git               |",
        "| ------------------------- | ------------------------ "
        "| ---------------------- |",
        "| split_refactor_vs_feature | PASS · 11c · 12t · $0.21 "
        "| PASS · 8c · 9t · $0.18 |",
        "",
        _CACHE_CAVEAT,
    ]


def test_render_summary_marks_missing_usage_and_counts_reported_runs() -> None:
    runs = [
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=0,
            passed=True,
            usage=_make_usage(turns=12, cost_usd=0.21),
        ),
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=1,
            passed=False,
            reason="solver-error",
            usage=None,
        ),
        _make_run(
            scenario=SCENARIOS[1],
            variant_index=0,
            passed=True,
            usage=_make_usage(turns=10, cost_usd=0.19),
        ),
        _make_run(
            scenario=SCENARIOS[1],
            variant_index=1,
            passed=True,
            usage=_make_usage(turns=8, cost_usd=0.15),
        ),
    ]

    lines = render_summary(runs=runs).splitlines()

    assert "| FAIL solver-error · —" in lines[2]
    assert "**1/2 · 7c · 8t · $0.15** (1/2 reported)" in lines[4]


def test_render_summary_states_the_reported_count_when_no_run_reported() -> None:
    runs = [
        _make_run(scenario=SCENARIOS[0], variant_index=0, passed=True, usage=None),
        _make_run(scenario=SCENARIOS[0], variant_index=1, passed=True, usage=None),
        _make_run(scenario=SCENARIOS[1], variant_index=0, passed=True, usage=None),
        _make_run(scenario=SCENARIOS[1], variant_index=1, passed=True, usage=None),
    ]

    lines = render_summary(runs=runs).splitlines()

    assert lines[4] == (
        "| **total**                 "
        "| **2/2 · —** (0/2 reported) | **2/2 · —** (0/2 reported) |"
    )


def test_render_summary_never_reports_a_sub_cent_cost_as_zero() -> None:
    runs = [
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=0,
            passed=True,
            usage=_make_usage(turns=1, cost_usd=0.0012),
        ),
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=1,
            passed=True,
            usage=_make_usage(turns=1, cost_usd=0.0),
        ),
    ]

    lines = render_summary(runs=runs).splitlines()

    assert "PASS · 0c · 1t · <$0.01" in lines[2]
    assert "PASS · 0c · 1t · $0.00" in lines[2]


def test_render_summary_lists_only_reasons_that_occurred_in_grader_order() -> None:
    runs = [
        _make_run(
            scenario=SCENARIOS[0],
            variant_index=1,
            passed=False,
            reason="leftover-untracked",
            usage=_make_usage(turns=9, cost_usd=0.18),
        ),
        _make_run(
            scenario=SCENARIOS[1],
            variant_index=1,
            passed=False,
            reason="partition",
            usage=_make_usage(turns=9, cost_usd=0.18),
        ),
    ]

    lines = render_summary(runs=runs).splitlines()

    # The `- ` prefix matters: consecutive bare lines collapse into one
    # rendered paragraph, which would make a pasted legend unreadable.
    assert lines[-2:] == [
        f"- partition: {REASON_LEGEND['partition']}",
        f"- leftover-untracked: {REASON_LEGEND['leftover-untracked']}",
    ]


def test_render_summary_reports_a_median_and_range_over_repeats() -> None:
    runs = [
        *_make_repeats(
            scenario=SCENARIOS[0],
            variant_index=0,
            samples=[
                (True, None, 13, 0.21),
                (True, None, 14, 0.23),
                (True, None, 13, 0.22),
            ],
        ),
        *_make_repeats(
            scenario=SCENARIOS[0],
            variant_index=1,
            samples=[
                (False, "order", 19, 0.31),
                (True, None, 22, 0.36),
                (False, "order", 20, 0.33),
            ],
        ),
        *_make_repeats(
            scenario=SCENARIOS[1],
            variant_index=0,
            samples=[
                (True, None, 10, 0.19),
                (True, None, 10, 0.19),
                (True, None, 10, 0.19),
            ],
        ),
        *_make_repeats(
            scenario=SCENARIOS[1],
            variant_index=1,
            samples=[
                (False, "leftover-worktree", 16, 0.28),
                (False, "leftover-worktree", 17, 0.29),
                (False, "leftover-worktree", 15, 0.26),
            ],
        ),
    ]

    assert render_summary(runs=runs).splitlines() == [
        "| Task                      "
        "| git-hunk                                                   "
        "| bare-git                              "
        "                                       |",
        "| ------------------------- "
        "| ---------------------------------------------------------- "
        "| --------------------------------------"
        "-------------------------------------- |",
        "| split_refactor_vs_feature "
        "| PASS 3/3 · 12c [12-13] · 13t [13-14] · $0.22 [$0.21-$0.23] "
        "| MIXED 1/3 order · 19c [18-21] "
        "· 20t [19-22] · $0.33 [$0.31-$0.36]            |",
        "| separate_mixed_hunks      "
        "| PASS 3/3 · 9c · 10t · $0.19                                "
        "| FAIL 0/3 leftover-worktree · 15c [14-16] "
        "· 16t [15-17] · $0.28 [$0.26-$0.29] |",
        "| **total**                 "
        "| **2/2 · 21c [21-22] · 23t [23-24] · $0.41 [$0.40-$0.42]**  "
        "| **0/2 (1 mixed) · 34c [32-37] "
        "· 36t [34-39] · $0.61 [$0.57-$0.65]**          |",
        "",
        f"{_CACHE_CAVEAT} {_REPEAT_CAVEAT}",
        "",
        f"- order: {REASON_LEGEND['order']}",
        f"- leftover-worktree: {REASON_LEGEND['leftover-worktree']}",
    ]


def test_render_summary_never_shows_a_variant_that_failed_a_repeat_as_a_pass() -> None:
    runs = _make_repeats(
        scenario=SCENARIOS[0],
        variant_index=0,
        samples=[
            (True, None, 10, 0.19),
            (True, None, 10, 0.19),
            (False, "order", 10, 0.19),
        ],
    )

    cell = render_summary(runs=runs).splitlines()[2]

    assert "MIXED 2/3 order" in cell
    assert "PASS" not in cell


def test_render_summary_names_every_reason_a_mixed_cell_hit_in_grader_order() -> None:
    runs = _make_repeats(
        scenario=SCENARIOS[0],
        variant_index=0,
        samples=[
            (False, "order", 10, 0.19),
            (True, None, 10, 0.19),
            (False, "partition", 10, 0.19),
        ],
    )

    lines = render_summary(runs=runs).splitlines()

    assert "MIXED 1/3 partition, order" in lines[2]
    assert lines[-2:] == [
        f"- partition: {REASON_LEGEND['partition']}",
        f"- order: {REASON_LEGEND['order']}",
    ]


def test_render_summary_reports_a_median_between_two_repeats() -> None:
    runs = _make_repeats(
        scenario=SCENARIOS[0],
        variant_index=0,
        samples=[(True, None, 13, 0.21), (True, None, 14, 0.23)],
    )

    assert render_summary(runs=runs).splitlines()[2] == (
        "| split_refactor_vs_feature "
        "| PASS 2/2 · 12.5c [12-13] · 13.5t [13-14] · $0.22 [$0.21-$0.23] |"
    )


def test_render_summary_omits_a_range_that_two_repeats_render_identically() -> None:
    runs = _make_repeats(
        scenario=SCENARIOS[0],
        variant_index=0,
        samples=[(True, None, 10, 0.2101), (True, None, 10, 0.2149)],
    )

    # Costs that both round to $0.21 must not render as the range $0.21-$0.21.
    assert "PASS 2/2 · 9c · 10t · $0.21 |" in render_summary(runs=runs).splitlines()[2]


def test_render_summary_says_when_only_some_repeats_reported_usage() -> None:
    runs = [
        *_make_repeats(
            scenario=SCENARIOS[0],
            variant_index=0,
            samples=[(True, None, 10, 0.19), (True, None, 10, 0.19)],
        ),
        _make_run(
            scenario=SCENARIOS[0], variant_index=0, passed=True, usage=None, repeat=3
        ),
    ]

    assert (
        "PASS 3/3 · 9c · 10t · $0.19 (2/3 reported)"
        in (render_summary(runs=runs).splitlines()[2])
    )


def test_render_summary_keeps_the_sub_cent_floor_inside_a_repeat_range() -> None:
    runs = _make_repeats(
        scenario=SCENARIOS[0],
        variant_index=0,
        samples=[(True, None, 1, 0.0012), (True, None, 1, 0.02)],
    )

    assert (
        "PASS 2/2 · 0c · 1t · $0.01 [<$0.01-$0.02]"
        in (render_summary(runs=runs).splitlines()[2])
    )


def test_render_summary_keeps_a_mixed_task_out_of_the_total_pass_count() -> None:
    runs = [
        *_make_repeats(
            scenario=SCENARIOS[0],
            variant_index=0,
            samples=[(True, None, 10, 0.19), (False, "order", 10, 0.19)],
        ),
        *_make_repeats(
            scenario=SCENARIOS[1],
            variant_index=0,
            samples=[(True, None, 10, 0.19), (True, None, 10, 0.19)],
        ),
    ]

    total = render_summary(runs=runs).splitlines()[4]

    assert total == (
        "| **total**                 | **1/2 (1 mixed) · 18c · 20t · $0.38** |"
    )


def test_render_summary_counts_reported_repeats_rather_than_task_variants() -> None:
    runs = [
        *_make_repeats(
            scenario=SCENARIOS[0],
            variant_index=0,
            samples=[(True, None, 10, 0.19), (True, None, 10, 0.19)],
        ),
        *_make_repeats(
            scenario=SCENARIOS[1],
            variant_index=0,
            samples=[(True, None, 10, 0.19), (True, None, 10, 0.19)],
        ),
    ]
    runs[1] = _make_run(
        scenario=SCENARIOS[0], variant_index=0, passed=True, usage=None, repeat=2
    )

    total = render_summary(runs=runs).splitlines()[4]

    assert "**2/2 · 18c · 20t · $0.38** (3/4 reported)" in total


def test_render_summary_is_empty_without_runs() -> None:
    assert render_summary(runs=[]) == ""


def test_reason_legend_matches_every_grader_failure_reason_in_order() -> None:
    assert list(REASON_LEGEND) == list(get_args(FailureReason))
