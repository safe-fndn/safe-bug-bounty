import contextlib
import json

import boa
import pytest
from eth.exceptions import Revert
from eth_abi import encode
from eth_utils import keccak
from hexbytes import HexBytes

import claim
import common

SUBMISSION = common.compute_submission_hash("alice@example.com", "Reentrancy")
OWNER = "0x0000000000000000000000000000000000005afe"
BOND_ID = "0x" + "ab" * 32


def printed(output, label):
    """The value printed after `label:`."""
    return output.split(f"{label}:")[1].split()[0]


@contextlib.contextmanager
def reverts(reason):
    """
    Expects a `raw_call` (as in `execute_bundle`) to revert with `reason`.
    `boa.reverts` does not catch these reverts, which are raised as the EVM's
    `Revert` with the raw `Error(string)` output.
    """
    with pytest.raises(Revert) as error:
        yield
    assert error.value.args == (
        keccak(text="Error(string)")[:4] + encode(["string"], [reason]),
    )


@pytest.fixture
def bonded(factory_bond, token, alice, amount):
    """The ID of a bond that `alice` posts on `factory_bond`."""
    with boa.env.prank(alice):
        token.approve(factory_bond, amount)
        return factory_bond.bond(SUBMISSION)


@pytest.fixture
def write_claim(token, amount, lockup, tmp_path, capsys):
    """
    A function that writes the claim bundle of `bond_id` for `owner` against
    `factory_bond`, and returns its path and the script's output.
    """

    def write(bond_id, owner):
        path = tmp_path / "claim.json"
        argv = ["--owner", str(owner), "--bond-id", HexBytes(bond_id).to_0x_hex()]
        argv += ["--token", str(token.address), "--amount", str(amount)]
        argv += ["--lockup", str(lockup), "--out", str(path)]
        claim.main(argv)
        return path, capsys.readouterr().out

    return write


def test_main(
    bonded,
    factory_bond,
    token,
    alice,
    amount,
    lockup,
    write_claim,
    execute_bundle,
):
    path, output = write_claim(bonded, alice)
    assert printed(output, "Bond ID") == HexBytes(bonded).to_0x_hex()
    assert printed(output, "BountyBond") == factory_bond.address
    assert "on chain ID 1\n" in output
    assert printed(output, "Owner") == alice
    assert printed(output, "Amount returned") == str(amount)
    assert '"locked"' in output
    assert printed(output, "Transaction bundle") == str(path)

    bundle = json.loads(path.read_text())
    assert bundle["meta"] == {"createdFromSafeAddress": alice}
    [tx] = bundle["transactions"]
    assert tx["to"] == factory_bond.address
    assert tx["data"] is None
    assert tx["contractMethod"]["name"] == "claim"
    assert tx["contractInputsValues"] == {"bond_id": HexBytes(bonded).to_0x_hex()}

    # Before the lockup has passed, the claim reverts.
    unlock = boa.env.timestamp + lockup
    boa.env.time_travel(seconds=lockup - 1)
    with reverts("locked"):
        execute_bundle(path, sender=alice)

    # Once it has, the Safe gets the bond amount back.
    boa.env.time_travel(seconds=1)
    assert boa.env.timestamp == unlock
    balance = token.balanceOf(alice)
    execute_bundle(path, sender=alice)
    assert factory_bond.bonds(bonded) == (alice, 0)
    assert token.balanceOf(alice) == balance + amount
    assert token.balanceOf(factory_bond) == 0

    # A claimed bond cannot be claimed again.
    with reverts("already claimed"):
        execute_bundle(path, sender=alice)


def test_main_not_owner(bonded, alice, bob, lockup, write_claim, execute_bundle):
    # The bundle is for the owner's Safe, but another account executes it.
    path, _ = write_claim(bonded, alice)
    boa.env.time_travel(seconds=lockup)
    with reverts("not owner"):
        execute_bundle(path, sender=bob)


def test_main_unknown_bond(factory_bond, alice, write_claim, execute_bundle):
    path, _ = write_claim(SUBMISSION, alice)
    with reverts("unknown bond"):
        execute_bundle(path, sender=alice)


def test_main_defaults(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    claim.main(["--owner", OWNER, "--bond-id", "0x" + "AB" * 32])
    output = capsys.readouterr().out

    address = common.bond_address(common.parser("test").parse_args([]))
    owner = common.parse_address(OWNER)
    assert printed(output, "Bond ID") == BOND_ID
    assert printed(output, "BountyBond") == address
    assert "on chain ID 1\n" in output
    assert printed(output, "Owner") == owner
    assert f"Amount returned: {1337 * 10**18} of token {common.SAFE_TOKEN}" in output

    path = tmp_path / "bundles" / "claim-abababab.json"
    assert printed(output, "Transaction bundle") == "bundles/claim-abababab.json"
    bundle = json.loads(path.read_text())
    assert bundle["chainId"] == "1"
    assert bundle["meta"] == {"createdFromSafeAddress": owner}
    assert bundle["transactions"] == [
        {
            "to": address,
            "value": "0",
            "data": None,
            "contractMethod": {
                "inputs": [
                    {"internalType": "bytes32", "name": "bond_id", "type": "bytes32"}
                ],
                "name": "claim",
                "payable": False,
            },
            "contractInputsValues": {"bond_id": BOND_ID},
        }
    ]


@pytest.mark.parametrize(
    "argv, message",
    [
        (
            ["--bond-id", BOND_ID],
            "the following arguments are required: --owner",
        ),
        (
            ["--owner", "0x1234", "--bond-id", BOND_ID],
            "argument --owner: invalid address: 0x1234",
        ),
        (
            ["--owner", OWNER],
            "the following arguments are required: --bond-id",
        ),
        (
            ["--owner", OWNER, "--bond-id", "0x1234"],
            "argument --bond-id: not 32 bytes of hex: 0x1234",
        ),
        (
            ["--owner", OWNER, "--bond-id", BOND_ID[2:]],
            f"argument --bond-id: not 32 bytes of hex: {BOND_ID[2:]}",
        ),
    ],
)
def test_main_invalid(argv, message, tmp_path, capsys):
    with pytest.raises(SystemExit) as exit:
        claim.main(argv + ["--out", str(tmp_path / "claim.json")])
    assert exit.value.code == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "claim.json").exists()
