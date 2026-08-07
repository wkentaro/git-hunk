import pytest

from eval.demonstration import Scenario
from eval.demonstration import StartingState
from eval.demonstration import build_demonstration_repository
from eval.demonstration import make_osam_scenario
from eval.demonstration import make_pricing_scenario
from eval.repo import GitRepo


@pytest.fixture
def pricing_scenario() -> Scenario:
    return make_pricing_scenario()


@pytest.fixture
def osam_scenario() -> Scenario:
    return make_osam_scenario()


@pytest.fixture
def pricing_repo(
    eval_repo: GitRepo, pricing_scenario: Scenario
) -> tuple[GitRepo, StartingState]:
    starting_state = build_demonstration_repository(
        repo=eval_repo, scenario=pricing_scenario
    )
    return eval_repo, starting_state


@pytest.fixture
def osam_repo(
    eval_repo: GitRepo, osam_scenario: Scenario
) -> tuple[GitRepo, StartingState]:
    starting_state = build_demonstration_repository(
        repo=eval_repo, scenario=osam_scenario
    )
    return eval_repo, starting_state
