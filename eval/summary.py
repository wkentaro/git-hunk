from collections.abc import Iterable
from typing import Final

from eval.grader import FailureReason
from eval.model import TaskRun
from eval.model import TraceUsage

_CACHE_CAVEAT: Final = (
    "{second} runs second and may read cache written by the {first} run; "
    "costs are not order-neutral."
)

REASON_LEGEND: Final[dict[FailureReason, str]] = {
    "partition": "commits do not match the required change groups",
    "order": "a required commit order constraint is violated",
    "final-tree": "the final HEAD tree does not match the expected files",
    "leftover-index": "the index does not match HEAD",
    "leftover-worktree": "tracked worktree files do not match the expected state",
    "leftover-untracked": "untracked files do not match the expected state",
    "solver-error": "the model run failed before grading",
}

_MISSING_METRICS: Final = "—"

# A cost strictly below this rounds to $0.00 at cent precision, which would read
# as free rather than as cheap.
_ROUNDS_TO_ZERO_USD: Final = 0.005


def render_summary(*, runs: list[TaskRun]) -> str:
    if not runs:
        return ""
    variant_names = _unique_in_order(values=(run.variant.name for run in runs))
    task_names = _unique_in_order(values=(run.scenario.task.name for run in runs))
    by_cell = {(run.scenario.task.name, run.variant.name): run for run in runs}

    rows = [["Task", *variant_names]]
    rows += [
        [
            task_name,
            *(
                _format_cell(run=by_cell[(task_name, variant_name)])
                for variant_name in variant_names
            ),
        ]
        for task_name in task_names
    ]
    if len(task_names) > 1:
        rows.append(
            [
                "**total**",
                *(
                    _format_total(
                        runs=[run for run in runs if run.variant.name == variant_name]
                    )
                    for variant_name in variant_names
                ),
            ]
        )

    lines = _format_table(rows=rows)
    if len(variant_names) == 2:
        first, second = variant_names
        lines += ["", _CACHE_CAVEAT.format(first=first, second=second)]
    legend = _format_legend(runs=runs)
    if legend:
        lines += ["", *legend]
    return "\n".join(lines)


def _unique_in_order(*, values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _format_cell(*, run: TaskRun) -> str:
    outcome = "PASS" if run.result.passed else f"FAIL {run.result.reason}"
    usages = [] if run.usage is None else [run.usage]
    return f"{outcome} · {_format_metrics(usages=usages)}"


def _format_total(*, runs: list[TaskRun]) -> str:
    passed = sum(run.result.passed for run in runs)
    usages = [run.usage for run in runs if run.usage is not None]
    total = f"**{passed}/{len(runs)} · {_format_metrics(usages=usages)}**"
    if len(usages) != len(runs):
        total += f" ({len(usages)}/{len(runs)} reported)"
    return total


def _format_metrics(*, usages: list[TraceUsage]) -> str:
    if not usages:
        return _MISSING_METRICS
    tool_calls = sum(usage.tool_calls for usage in usages)
    turns = sum(usage.turns for usage in usages)
    cost = _format_cost(value=sum(usage.cost_usd for usage in usages))
    return f"{tool_calls}c · {turns}t · {cost}"


def _format_cost(*, value: float) -> str:
    if 0 < value < _ROUNDS_TO_ZERO_USD:
        return "<$0.01"
    return f"${value:.2f}"


def _format_legend(*, runs: list[TaskRun]) -> list[str]:
    reasons = {run.result.reason for run in runs if not run.result.passed}
    return [
        f"- {reason}: {gloss}"
        for reason, gloss in REASON_LEGEND.items()
        if reason in reasons
    ]


def _format_table(*, rows: list[list[str]]) -> list[str]:
    widths = [max(len(cell) for cell in column) for column in zip(*rows)]
    header, *body = rows
    separator: list[str] = ["-" * width for width in widths]
    return [
        _format_row(cells=cells, widths=widths) for cells in (header, separator, *body)
    ]


def _format_row(*, cells: list[str], widths: list[int]) -> str:
    padded = " | ".join(cell.ljust(width) for cell, width in zip(cells, widths))
    return f"| {padded} |"
