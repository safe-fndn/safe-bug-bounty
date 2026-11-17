from pathlib import Path

import boa
import pytest

MOCKS = Path(__file__).parent / "mocks"


@pytest.fixture
def false_token(deployer):
    with boa.env.prank(deployer):
        return boa.load(MOCKS / "FalseToken.vy")
