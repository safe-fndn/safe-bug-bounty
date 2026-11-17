import argparse
import json
import re
import time

import boa
import pytest
from eth_abi import encode
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from hexbytes import HexBytes

import common

EMAIL = "alice@example.com"
SUBJECT = "Reentrancy in Vault.withdraw (0x1a2b3c4d)"
TO = "0x0000000000000000000000000000000000000001"
SAFE = "0x5aFE3855358E112B5647B952709E6165e1c1eEEe"
CLAIM = {
    "inputs": [{"name": "bond_id", "type": "bytes32", "internalType": "bytes32"}],
    "name": "claim",
    "payable": False,
}

SUBMISSION_FIELDS = [
    {"name": "email", "type": "string"},
    {"name": "subject", "type": "string"},
]


def typed_data_hash(message):
    """The EIP-712 hash of an `eth_account` `SignableMessage`."""
    return keccak(b"\x19" + message.version + message.header + message.body)


def test_compute_submission_hash():
    # eth_account's EIP-712 `hashStruct` of the `Submission` message.
    message = encode_typed_data(
        full_message={
            "types": {"EIP712Domain": [], "Submission": SUBMISSION_FIELDS},
            "primaryType": "Submission",
            "domain": {},
            "message": {"email": EMAIL, "subject": SUBJECT},
        }
    )
    assert common.compute_submission_hash(EMAIL, SUBJECT) == message.body


def test_compute_submission_hash_fields():
    # The strings are hashed separately, so moving text between them changes
    # the hash.
    assert common.compute_submission_hash("ab", "c") != common.compute_submission_hash(
        "a", "bc"
    )


def test_compute_bond_id(chain_id, alice):
    contract = boa.env.generate_address("contract")
    message = encode_typed_data(
        full_message={
            "types": {
                "EIP712Domain": [
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "Bond": [
                    {"name": "owner", "type": "address"},
                    {"name": "submission", "type": "Submission"},
                ],
                "Submission": SUBMISSION_FIELDS,
            },
            "primaryType": "Bond",
            "domain": {"chainId": chain_id, "verifyingContract": str(contract)},
            "message": {
                "owner": str(alice),
                "submission": {"email": EMAIL, "subject": SUBJECT},
            },
        }
    )
    submission = common.compute_submission_hash(EMAIL, SUBJECT)
    assert common.compute_domain_separator(chain_id, contract) == message.header
    assert common.compute_bond_id(
        chain_id, contract, alice, submission
    ) == typed_data_hash(message)


def test_compute_bond_id_contract(bond, token, alice, amount, chain_id):
    submission = common.compute_submission_hash(EMAIL, SUBJECT)
    with boa.env.prank(alice):
        token.approve(bond, amount)
        bond_id = bond.bond(submission)

    assert bond.domainSeparator() == common.compute_domain_separator(
        chain_id, bond.address
    )
    assert bond_id == common.compute_bond_id(chain_id, bond.address, alice, submission)


def test_parser():
    parser = common.parser("test")
    args = parser.parse_args([])
    assert args.chain_id == 1
    assert args.token == "0x5aFE3855358E112B5647B952709E6165e1c1eEEe"
    assert args.amount == 1337 * 10**18
    assert args.lockup == 30 * 24 * 60 * 60
    assert args.create2_salt == bytes(32)

    token = "0x0000000000000000000000000000000000000001"
    args = parser.parse_args(
        ["--chain-id", "100", "--token", token, "--amount", "1e18"]
        + ["--lockup", "60", "--create2-salt", "0x" + "42" * 32]
    )
    assert args.chain_id == 100
    assert args.token == token
    assert args.amount == 10**18
    assert args.lockup == 60
    assert args.create2_salt == b"\x42" * 32


@pytest.mark.parametrize(
    "argv",
    [["--chain-id", "gnosis"], ["--token", "0x5afe"], ["--amount", "1.5"]],
)
def test_parser_invalid(argv, capsys):
    with pytest.raises(SystemExit) as exit:
        common.parser("test").parse_args(argv)
    assert exit.value.code == 2
    assert f"argument {argv[0]}" in capsys.readouterr().err


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1337e18", 1337 * 10**18),
        ("1337E18", 1337 * 10**18),
        ("1.5e18", 15 * 10**17),
        ("2592000", 2_592_000),
        ("2_592_000", 2_592_000),
        ("0", 0),
        (str(2**256 - 1), 2**256 - 1),
    ],
)
def test_parse_uint(value, expected):
    assert common.parse_uint(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "abc", "1.5", "1e-1", "-1", "nan", "inf", str(2**256), "1e78", "1e999999999"],
)
def test_parse_uint_invalid(value):
    with pytest.raises(argparse.ArgumentTypeError, match="not a uint256"):
        common.parse_uint(value)


def test_parse_address():
    address = "0x5aFE3855358E112B5647B952709E6165e1c1eEEe"
    assert common.parse_address(address.lower()) == address
    with pytest.raises(argparse.ArgumentTypeError):
        common.parse_address("0x5afe")
    with pytest.raises(argparse.ArgumentTypeError):
        # Bad checksum: the case of one letter is flipped.
        common.parse_address(address.replace("aFE", "AFE"))


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0x" + "00" * 32, bytes(32)),
        ("0x" + "aB" * 32, b"\xab" * 32),
    ],
)
def test_parse_bytes32(value, expected):
    assert common.parse_bytes32(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "ab" * 32,
        "0X" + "ab" * 32,
        "0x" + "ab" * 31,
        "0x" + "ab" * 33,
        "0x" + "zz" * 32,
        "0x" + "ab" * 31 + " a",
        "0",
    ],
)
def test_parse_bytes32_invalid(value):
    with pytest.raises(argparse.ArgumentTypeError, match="not 32 bytes of hex"):
        common.parse_bytes32(value)


def test_run():
    def main():
        raise common.ScriptError("boom")

    with pytest.raises(SystemExit, match="error: boom"):
        common.run(main)


def test_compile_bond(token, amount, lockup):
    compiled = common.compile_bond()
    args = encode(
        ["address", "uint256", "uint256"], [str(token.address), amount, lockup]
    )
    address, _ = boa.env.deploy_code(bytecode=HexBytes(compiled.bytecode) + args)
    bond = boa.load_partial(common.CONTRACT).at(address)
    assert bond.TOKEN() == token.address
    assert bond.AMOUNT() == amount
    assert bond.LOCKUP() == lockup


def test_transaction_bundle():
    transactions = [
        {"to": TO, "data": "0x01"},
        {
            "to": TO,
            "value": "42",
            "contractMethod": CLAIM,
            "contractInputsValues": {"bond_id": "0x" + "00" * 32},
        },
    ]
    bundle = common.transaction_bundle(100, transactions, 1337)
    assert bundle == {
        "version": "1.0",
        "chainId": "100",
        "createdAt": 1337,
        "meta": {},
        "transactions": [
            {
                "to": TO,
                "value": "0",
                "data": "0x01",
                "contractMethod": None,
                "contractInputsValues": None,
            },
            {
                "to": TO,
                "value": "42",
                "data": None,
                "contractMethod": CLAIM,
                "contractInputsValues": {"bond_id": "0x" + "00" * 32},
            },
        ],
    }
    assert common.transaction_bundle(100, transactions, 1337) == bundle


def test_transaction_bundle_now(monkeypatch):
    monkeypatch.setattr(time, "time_ns", lambda: 1337 * 10**6 + 42)
    assert common.transaction_bundle(1, [])["createdAt"] == 1337


def test_transaction_bundle_safe():
    bundle = common.transaction_bundle(1, [], 1337, safe=SAFE)
    assert bundle["meta"] == {"createdFromSafeAddress": SAFE}


def test_transaction_bundle_data_and_method():
    with pytest.raises(ValueError):
        common.transaction_bundle(
            1, [{"to": TO, "data": "0x", "contractMethod": CLAIM}], 1337
        )


def test_write_transaction_bundle(tmp_path):
    path = tmp_path / "bundles" / "test.json"
    transactions = [{"to": TO, "data": "0x"}]

    written = common.write_transaction_bundle(str(path), 1, transactions, 1337, SAFE)
    assert written == path
    text = path.read_text()
    assert text.startswith('{\n\t"chainId": "1",\n')
    assert text.endswith("}\n")
    assert json.loads(text) == common.transaction_bundle(1, transactions, 1337, SAFE)


def test_bond_address(factory, token, alice, chain_id):
    args = common.parser("test").parse_args(
        ["--token", str(token.address), "--amount", "1e18", "--lockup", "60"]
        + ["--create2-salt", "0x" + "42" * 32]
    )
    code = common.init_code(args.token, args.amount, args.lockup)
    computation = boa.env.raw_call(common.FACTORY, data=args.create2_salt + code)
    address = common.bond_address(args)
    assert address == common.parse_address("0x" + computation.output.hex())

    bond = boa.load_partial(common.CONTRACT).at(address)
    assert bond.TOKEN() == token.address
    assert bond.AMOUNT() == 10**18
    assert bond.LOCKUP() == 60

    # The deployed contract computes the bond IDs that the scripts expect.
    submission = common.compute_submission_hash(EMAIL, SUBJECT)
    with boa.env.prank(alice):
        token.approve(bond, 10**18)
        bond_id = bond.bond(submission)
    assert bond_id == common.compute_bond_id(chain_id, address, alice, submission)


def test_bond_address_salt():
    parser = common.parser("test")
    addresses = {
        common.bond_address(parser.parse_args(["--create2-salt", salt]))
        for salt in ("0x" + "00" * 32, "0x" + "00" * 31 + "01")
    }
    assert len(addresses) == 2


def test_contract_method():
    assert common.contract_method(common.compile_bond().abi, "bond") == {
        "inputs": [
            {"internalType": "bytes32", "name": "submission", "type": "bytes32"}
        ],
        "name": "bond",
        "payable": False,
    }
    assert common.contract_method(common.compile_bond().abi, "claim") == CLAIM
    assert common.contract_method(common.ERC20_ABI, "approve") == {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "value", "type": "uint256"},
        ],
        "name": "approve",
        "payable": False,
    }


@pytest.mark.parametrize(
    "email, expected",
    [
        ("alice@example.com", "alice@example.com"),
        ("  Alice@Example.COM\t\n", "alice@example.com"),
    ],
)
def test_normalize_email(email, expected):
    assert common.normalize_email(email) == expected


@pytest.mark.parametrize("email", ["", " \t\n"])
def test_normalize_email_invalid(email):
    with pytest.raises(ValueError, match="the email is empty"):
        common.normalize_email(email)


@pytest.mark.parametrize(
    "subject, expected",
    [
        (SUBJECT, SUBJECT),
        # Trimmed, with case and inner whitespace kept.
        ("  Reentrancy in  VAULT.withdraw \r\n", "Reentrancy in  VAULT.withdraw"),
        # Every printable ASCII character is allowed.
        ("".join(map(chr, range(0x21, 0x7F))), "".join(map(chr, range(0x21, 0x7F)))),
    ],
)
def test_normalize_subject(subject, expected):
    assert common.normalize_subject(subject) == expected


@pytest.mark.parametrize(
    "subject, char",
    [
        ("Reentrancy\tin Vault", "\t"),
        ("Reentrancy\nin Vault", "\n"),
        ("Reentrancy in Vault\x00", "\x00"),
        ("Reentrancy in Vault\x7f", "\x7f"),
        ("Reentrancy in Vault 🐛", "🐛"),
        ("Réentrancy in Vault", "é"),
        # Only ASCII whitespace is trimmed.
        (" Reentrancy in Vault", " "),
    ],
)
def test_normalize_subject_invalid(subject, char):
    with pytest.raises(ValueError, match="the subject is not printable ASCII") as e:
        common.normalize_subject(subject)
    assert str(e.value).endswith(repr(char))


@pytest.mark.parametrize("subject", ["", " \t\n"])
def test_normalize_subject_empty(subject):
    with pytest.raises(ValueError, match="the subject is empty"):
        common.normalize_subject(subject)


def test_salt_subject(monkeypatch):
    def token_hex(nbytes):
        assert nbytes == 4
        return "1a2b3c4d"

    monkeypatch.setattr(common.secrets, "token_hex", token_hex)
    salted = common.salt_subject("Reentrancy in Vault.withdraw")
    assert salted == SUBJECT
    assert common.normalize_subject(salted) == salted


def test_salt_subject_random():
    salted = {common.salt_subject("Reentrancy") for _ in range(8)}
    assert len(salted) == 8
    for subject in salted:
        assert re.fullmatch(r"Reentrancy \(0x[0-9a-f]{8}\)", subject)
