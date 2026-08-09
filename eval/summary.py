import dataclasses
import statistics
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
from typing import Final

from eval.grader import FailureReason
from eval.model import TaskRun
from eval.model import TraceUsage

_CACHE_CAVEAT: Final = (
    "{second} runs second and may read cache written by the {first} run; "
    "costs are not order-neutral."
)

_REPEAT_CAVEAT: Final = (
    "Only the first repeat starts cold, so a cost range mixes cache warmup with "
    "run-to-run noise."
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


@dataclasses.dataclass(frozen=True)
class _Spread:
    """One metric over the repeats of a cell: a median and the observed range."""

    median: float
    minimum: float
    maximum: float

    @classmethod
    def of(cls, *, values: Sequence[float]) -> "_Spread":
        return cls(
            median=statistics.median(values),
            minimum=min(values),
            maximum=max(values),
        )

    @classmethod
    def total(cls, *, spreads: list["_Spread"]) -> "_Spread":
        # Summing each statistic separately keeps the total's centre a sum of
        # typical tasks and its bracket the best and worst case of the whole
        # selection, rather than pairing repeats of unrelated tasks.
        return cls(
            median=sum(spread.median for spread in spreads),
            minimum=sum(spread.minimum for spread in spreads),
            maximum=sum(spread.maximum for spread in spreads),
        )


@dataclasses.dataclass(frozen=True)
class _Metrics:
    tool_calls: _Spread
    turns: _Spread
    cost_usd: _Spread

    @classmethod
    def of(cls, *, usages: list[TraceUsage]) -> "_Metrics":
        return cls(
            tool_calls=_Spread.of(values=[usage.tool_calls for usage in usages]),
            turns=_Spread.of(values=[usage.turns for usage in usages]),
            cost_usd=_Spread.of(values=[usage.cost_usd for usage in usages]),
        )

    @classmethod
    def total(cls, *, metrics: list["_Metrics"]) -> "_Metrics":
        return cls(
            tool_calls=_Spread.total(spreads=[metric.tool_calls for metric in metrics]),
            turns=_Spread.total(spreads=[metric.turns for metric in metrics]),
            cost_usd=_Spread.total(spreads=[metric.cost_usd for metric in metrics]),
        )

    def render(self) -> str:
        return " · ".join(
            (
                _format_spread(spread=self.tool_calls, render=_format_count, unit="c"),
                _format_spread(spread=self.turns, render=_format_count, unit="t"),
                _format_spread(spread=self.cost_usd, render=_format_cost),
            )
        )


def render_summary(*, runs: list[TaskRun]) -> str:
    if not runs:
        return ""
    variant_names = _unique_in_order(values=(run.variant.name for run in runs))
    task_names = _unique_in_order(values=(run.scenario.task.name for run in runs))
    cells: dict[tuple[str, str], list[TaskRun]] = {}
    for run in runs:
        cells.setdefault((run.scenario.task.name, run.variant.name), []).append(run)

    rows = [["Task", *variant_names]]
    rows += [
        [
            task_name,
            *(
                _format_cell(runs=cells[(task_name, variant_name)])
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
                        task_cells=[
                            cells[(task_name, variant_name)] for task_name in task_names
                        ]
                    )
                    for variant_name in variant_names
                ),
            ]
        )

    lines = _format_table(rows=rows)
    caveats: list[str] = []
    if len(variant_names) == 2:
        first, second = variant_names
        caveats.append(_CACHE_CAVEAT.format(first=first, second=second))
    if any(len(cell) > 1 for cell in cells.values()):
        caveats.append(_REPEAT_CAVEAT)
    if caveats:
        # One paragraph, not one line each: consecutive bare lines would render
        # as a single paragraph anyway, so join them deliberately.
        lines += ["", " ".join(caveats)]
    legend = _format_legend(runs=runs)
    if legend:
        lines += ["", *legend]
    return "\n".join(lines)


def _unique_in_order(*, values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _format_cell(*, runs: list[TaskRun]) -> str:
    usages = _reported_usages(runs=runs)
    metrics = _MISSING_METRICS if not usages else _Metrics.of(usages=usages).render()
    cell = f"{_format_outcome(runs=runs)} · {metrics}"
    if len(runs) == 1:
        # A single sample says all it can with `—`; the note below would be new
        # output for an unrepeated run.
        return cell
    # Without this the median of the repeats that did report would read as the
    # median of every repeat.
    return cell + _format_reported_note(reported=len(usages), total=len(runs))


def _format_outcome(*, runs: list[TaskRun]) -> str:
    passed = sum(run.result.passed for run in runs)
    if len(runs) == 1:
        # A single sample keeps the historical wording: there is no fraction to
        # report and no repeat that could disagree with it.
        return "PASS" if passed else f"FAIL {runs[0].result.reason}"
    if _cell_passed(cell=runs):
        return f"PASS {passed}/{len(runs)}"
    # A variant that failed any repeat must never read as a clean pass, so the
    # word itself changes rather than only the fraction beside it.
    label = "MIXED" if _cell_mixed(cell=runs) else "FAIL"
    reasons = ", ".join(_failure_reasons(runs=runs))
    return f"{label} {passed}/{len(runs)} {reasons}"


def _format_total(*, task_cells: list[list[TaskRun]]) -> str:
    reported = [_reported_usages(runs=cell) for cell in task_cells]
    metrics_by_cell = [_Metrics.of(usages=usages) for usages in reported if usages]
    metrics = (
        _MISSING_METRICS
        if not metrics_by_cell
        else _Metrics.total(metrics=metrics_by_cell).render()
    )
    passed = sum(_cell_passed(cell=cell) for cell in task_cells)
    mixed = sum(_cell_mixed(cell=cell) for cell in task_cells)
    mixed_note = f" ({mixed} mixed)" if mixed else ""
    total = f"**{passed}/{len(task_cells)}{mixed_note} · {metrics}**"
    return total + _format_reported_note(
        reported=sum(len(usages) for usages in reported),
        total=sum(len(cell) for cell in task_cells),
    )


def _format_reported_note(*, reported: int, total: int) -> str:
    if reported == total:
        return ""
    return f" ({reported}/{total} reported)"


def _cell_passed(*, cell: list[TaskRun]) -> bool:
    return all(run.result.passed for run in cell)


def _cell_mixed(*, cell: list[TaskRun]) -> bool:
    return any(run.result.passed for run in cell) and not _cell_passed(cell=cell)


def _reported_usages(*, runs: list[TaskRun]) -> list[TraceUsage]:
    return [run.usage for run in runs if run.usage is not None]


def _failure_reasons(*, runs: list[TaskRun]) -> list[FailureReason]:
    reasons = {run.result.reason for run in runs if not run.result.passed}
    return [reason for reason in REASON_LEGEND if reason in reasons]


def _format_spread(
    *, spread: _Spread, render: Callable[[float], str], unit: str = ""
) -> str:
    center = f"{render(spread.median)}{unit}"
    minimum = render(spread.minimum)
    maximum = render(spread.maximum)
    # Compare what the reader sees, not the raw floats: two costs that both
    # round to $0.21 would otherwise render as the range `[$0.21-$0.21]`.
    if minimum == maximum:
        return center
    # An ASCII range separator keeps every table row the same rendered width in
    # a terminal, where an en dash is an ambiguous-width character.
    return f"{center} [{minimum}-{maximum}]"


# The two renderers below take their value positionally, unlike the rest of this
# module, because `_format_spread` accepts one as a plain `Callable[[float], str]`.


def _format_count(value: float) -> str:
    # An even number of repeats can put the median between two samples; keeping
    # the half shows that rather than rounding it away.
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def _format_cost(value: float) -> str:
    if 0 < value < _ROUNDS_TO_ZERO_USD:
        return "<$0.01"
    return f"${value:.2f}"


def _format_legend(*, runs: list[TaskRun]) -> list[str]:
    return [
        f"- {reason}: {REASON_LEGEND[reason]}" for reason in _failure_reasons(runs=runs)
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
