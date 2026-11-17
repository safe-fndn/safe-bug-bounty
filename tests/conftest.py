from pathlib import Path

import boa
import pytest

TESTS = Path(__file__).parent
MOCKS = TESTS / "contracts" / "mocks"
CONTRACTS = TESTS.parent / "contracts"


@pytest.fixture
def initial_balance():
    return 1_000_000 * 10**18


@pytest.fixture
def amount():
    return 1337 * 10**18


@pytest.fixture
def lockup():
    return 30 * 24 * 60 * 60


@pytest.fixture
def deployer():
    return boa.env.eoa


@pytest.fixture
def alice():
    return boa.env.generate_address("alice")


@pytest.fixture
def bob():
    return boa.env.generate_address("bob")


@pytest.fixture
def token(deployer, alice, bob, initial_balance):
    with boa.env.prank(deployer):
        token = boa.load(MOCKS / "Token.vy")
    for account in (alice, bob):
        token.mint(account, initial_balance)
    return token


@pytest.fixture
def bond(deployer, token, amount, lockup):
    with boa.env.prank(deployer):
        return boa.load(CONTRACTS / "BountyBond.vy", token, amount, lockup)
