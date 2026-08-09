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
    )


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


def test_render_summary_is_empty_without_runs() -> None:
    assert render_summary(runs=[]) == ""


def test_reason_legend_matches_every_grader_failure_reason_in_order() -> None:
    assert list(REASON_LEGEND) == list(get_args(FailureReason))
