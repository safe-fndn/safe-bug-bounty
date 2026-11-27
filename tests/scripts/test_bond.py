import json

import boa
import pytest
from hexbytes import HexBytes

import bond
import common

EMAIL = "alice@example.com"
SUBJECT = "Reentrancy in Vault.withdraw"
OWNER = "0x0000000000000000000000000000000000005afe"
SALT = "1a2b3c4d5e6f708192a3b4c5d6e7f801"
SALTED = f"{SUBJECT} (0x{SALT})"


@pytest.fixture
def salt(monkeypatch):
    """Makes the subject salt `0x` followed by `SALT`."""
    monkeypatch.setattr(common.secrets, "token_hex", lambda nbytes: SALT)


def printed(output, label):
    """The value printed after `label:`."""
    return output.split(f"{label}:")[1].split()[0]


def test_main(
    salt, factory_bond, token, alice, amount, lockup, execute_bundle, tmp_path, capsys
):
    path = tmp_path / "bond.json"
    argv = ["--owner", str(alice), "--email", " Alice@Example.COM ", "--subject"]
    argv += [f" {SUBJECT}\n", "--token", str(token.address), "--amount", str(amount)]
    argv += ["--lockup", str(lockup), "--out", str(path)]
    bond.main(argv)
    output = capsys.readouterr().out

    # The subject is salted by default.
    submission = common.compute_submission_hash(EMAIL, SALTED)
    assert f"\n    {SALTED}\n" in output
    assert "random salt" in output
    assert printed(output, "Email") == EMAIL
    assert printed(output, "Submission hash") == HexBytes(submission).to_0x_hex()
    assert printed(output, "BountyBond") == factory_bond.address
    assert printed(output, "Owner") == alice
    assert f"Unlock:          {lockup} seconds (30 days) after" in output
    assert printed(output, "Transaction bundle") == str(path)

    bundle = json.loads(path.read_text())
    assert bundle["meta"] == {"createdFromSafeAddress": alice}
    approve, post = bundle["transactions"]
    assert approve["to"] == token.address
    assert approve["contractMethod"]["name"] == "approve"
    assert post["to"] == factory_bond.address
    assert post["contractMethod"]["name"] == "bond"

    # The Safe executes the bundle, and `bond` returns the printed bond ID.
    balance = token.balanceOf(alice)
    _, computation = execute_bundle(path, sender=alice)
    bond_id = computation.output
    assert HexBytes(bond_id).to_0x_hex() == printed(output, "Bond ID")
    assert factory_bond.bonds(bond_id) == (alice, boa.env.timestamp + lockup)
    assert token.balanceOf(alice) == balance - amount
    assert token.balanceOf(factory_bond) == amount
    assert token.allowance(alice, factory_bond) == 0


def test_main_no_salt(salt, tmp_path, capsys):
    path = tmp_path / "bond.json"
    argv = ["--owner", OWNER, "--email", EMAIL, "--subject", SUBJECT, "--no-salt"]
    bond.main(argv + ["--out", str(path)])
    output = capsys.readouterr().out

    submission = common.compute_submission_hash(EMAIL, SUBJECT)
    assert f"\n    {SUBJECT}\n" in output
    assert "random salt" not in output
    assert printed(output, "Submission hash") == HexBytes(submission).to_0x_hex()
    [_, post] = json.loads(path.read_text())["transactions"]
    assert post["contractInputsValues"] == {
        "submission": HexBytes(submission).to_0x_hex()
    }


def test_main_defaults(salt, monkeypatch, tmp_path, capsys, safe_token):
    monkeypatch.chdir(tmp_path)
    bond.main(["--owner", OWNER, "--email", EMAIL, "--subject", SUBJECT])
    output = capsys.readouterr().out

    address = common.bond_address(common.parser("test").parse_args([]))
    owner = common.parse_address(OWNER)
    submission = common.compute_submission_hash(EMAIL, SALTED)
    bond_id = common.compute_bond_id(1, address, owner, submission)
    assert f"\n    {SALTED}\n" in output
    assert printed(output, "Bond ID") == HexBytes(bond_id).to_0x_hex()
    assert printed(output, "BountyBond") == address

    path = tmp_path / "bundles" / f"bond-{bond_id.hex()[:8]}.json"
    bundle = json.loads(path.read_text())
    assert bundle["chainId"] == "1"
    assert bundle["meta"] == {"createdFromSafeAddress": owner}
    assert [tx["to"] for tx in bundle["transactions"]] == [safe_token, address]
    assert [tx["contractInputsValues"] for tx in bundle["transactions"]] == [
        {"spender": address, "value": str(1337 * 10**18)},
        {"submission": HexBytes(submission).to_0x_hex()},
    ]


@pytest.mark.parametrize(
    "argv, message",
    [
        (
            ["--email", EMAIL, "--subject", SUBJECT],
            "the following arguments are required: --owner",
        ),
        (
            ["--owner", "0x1234", "--email", EMAIL, "--subject", SUBJECT],
            "argument --owner: invalid address: 0x1234",
        ),
        (
            ["--owner", OWNER, "--email", " ", "--subject", SUBJECT],
            "argument --email: the email is empty",
        ),
        (
            ["--owner", OWNER, "--email", EMAIL, "--subject", "Bug\tin Vault"],
            "argument --subject: the subject is not printable ASCII: '\\t'",
        ),
        (
            ["--owner", OWNER, "--email", EMAIL, "--subject", "Bug in Vault 🐛"],
            "argument --subject: the subject is not printable ASCII: '🐛'",
        ),
    ],
)
def test_main_invalid(argv, message, tmp_path, capsys):
    with pytest.raises(SystemExit) as exit:
        bond.main(argv + ["--out", str(tmp_path / "bond.json")])
    assert exit.value.code == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "bond.json").exists()
