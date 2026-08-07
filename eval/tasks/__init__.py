from typing import Final

from eval.scenario import Scenario
from eval.tasks import drop_debug_lines
from eval.tasks import protect_unrelated_work
from eval.tasks import separate_mixed_hunks
from eval.tasks import split_refactor_vs_feature

SCENARIOS: Final[tuple[Scenario, ...]] = (
    split_refactor_vs_feature.SCENARIO,
    separate_mixed_hunks.SCENARIO,
    drop_debug_lines.SCENARIO,
    protect_unrelated_work.SCENARIO,
)
