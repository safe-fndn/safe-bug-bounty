import json

import boa
import pytest
from eth_abi import encode
from eth_utils import keccak
from hexbytes import HexBytes

import common

# The runtime code of the Safe singleton factory, from its deployment
# transaction in `safe-fndn/safe-singleton-factory` (`artifacts/1`).
FACTORY_CODE = HexBytes(
    "0x7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffe036016000"
    "81602082378035828234f58015156039578182fd5b8082525050506014600cf3"
)


@pytest.fixture
def chain_id():
    return boa.env.evm.patch.chain_id


@pytest.fixture
def factory():
    """The Safe singleton factory at its address."""
    boa.env.set_code(common.FACTORY, FACTORY_CODE)


@pytest.fixture
def factory_bond(factory, token, amount, lockup):
    """
    `BountyBond` deployed through the factory with the `token`, `amount` and
    `lockup` fixtures and the zero CREATE2 salt, as the scripts expect it.
    """
    code = common.init_code(token.address, amount, lockup)
    computation = boa.env.raw_call(common.FACTORY, data=bytes(32) + code)
    return boa.load_partial(common.CONTRACT).at(computation.output)


def calldata(tx):
    """
    The call data of a bundle transaction: its raw `data`, or its
    `contractMethod` encoded with its `contractInputsValues`, as the Transaction
    Builder does.
    """
    method = tx["contractMethod"]
    if method is None:
        return HexBytes(tx["data"])
    types = [param["type"] for param in method["inputs"]]
    values = []
    for param in method["inputs"]:
        value = tx["contractInputsValues"][param["name"]]
        if param["type"].startswith("uint"):
            value = int(value)
        elif param["type"].startswith("bytes"):
            value = HexBytes(value)
        values.append(value)
    selector = keccak(text=f"{method['name']}({','.join(types)})")[:4]
    return selector + encode(types, values)


@pytest.fixture
def execute_bundle():
    """
    A function that executes the transactions of the bundle at `path` in order,
    as `sender` (the Safe), and returns their computations.
    """

    def execute(path, sender=None):
        bundle = json.loads(path.read_text())
        assert bundle["chainId"] == str(boa.env.evm.patch.chain_id)
        return [
            boa.env.raw_call(
                tx["to"], sender=sender, value=int(tx["value"]), data=calldata(tx)
            )
            for tx in bundle["transactions"]
        ]

    return execute
