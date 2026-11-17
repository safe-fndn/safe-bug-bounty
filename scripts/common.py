"""Shared helpers for the `BountyBond` scripts."""

import argparse
import functools
import json
import secrets
import string
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

import vyper
from eth_abi import encode
from eth_utils import (
    is_checksum_address,
    is_hex_address,
    keccak,
    to_checksum_address,
)
from hexbytes import HexBytes

# EIP-712 type strings, as in `contracts/BountyBond.vy`.
DOMAIN_TYPE = "EIP712Domain(uint256 chainId,address verifyingContract)"
SUBMISSION_TYPE = "Submission(string email,string subject)"
BOND_TYPE = "Bond(address owner,Submission submission)" + SUBMISSION_TYPE

CONTRACT = Path(__file__).parents[1] / "contracts" / "BountyBond.vy"

# The default deployment parameters: the SAFE token (on Ethereum mainnet), 1337
# SAFE, 30 days and the zero `CREATE2` salt.
SAFE_TOKEN = "0x5aFE3855358E112B5647B952709E6165e1c1eEEe"
BOND_AMOUNT = "1337e18"
LOCKUP = "2592000"
CREATE2_SALT = "0x" + "00" * 32

# The Safe singleton factory, a `CREATE2` factory at the same address on every
# bytecode-compatible EVM chain. Its call data is a 32-byte salt followed by
# the init code.
FACTORY = "0x914d7Fec6aaC8cd542e72Bca78B30650d45643d7"

# The ERC20 functions that the scripts call, as an ABI.
ERC20_ABI = [
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]


def compute_submission_hash(email, subject):
    """
    The EIP-712 struct hash of `Submission{email, subject}`, the argument of
    `bond`. The email and subject must already be normalized.
    """
    return keccak(
        encode(
            ["bytes32", "bytes32", "bytes32"],
            [keccak(text=SUBMISSION_TYPE), keccak(text=email), keccak(text=subject)],
        )
    )


def compute_domain_separator(chain_id, contract):
    """The EIP-712 domain separator of the `BountyBond` at `contract`."""
    return keccak(
        encode(
            ["bytes32", "uint256", "address"],
            [keccak(text=DOMAIN_TYPE), chain_id, str(contract)],
        )
    )


def compute_bond_id(chain_id, contract, owner, submission_hash):
    """
    The bond ID that `bond(submission_hash)` returns when called by `owner` on
    the `BountyBond` at `contract`: the EIP-712 hash of `Bond{owner, submission}`.
    """
    struct_hash = keccak(
        encode(
            ["bytes32", "address", "bytes32"],
            [keccak(text=BOND_TYPE), str(owner), submission_hash],
        )
    )
    domain_separator = compute_domain_separator(chain_id, contract)
    return keccak(b"\x19\x01" + domain_separator + struct_hash)


class ScriptError(Exception):
    """An error that is shown to the user as a message, without a traceback."""


def run(main):
    """Runs a script's `main`, exiting with a message on a `ScriptError`."""
    try:
        main()
    except ScriptError as error:
        sys.exit(f"error: {error}")


def parser(description):
    """
    An argument parser with the options that all scripts take: the chain ID of
    the bundle, and the `BountyBond` deployment parameters, which determine the
    contract's address.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--chain-id",
        type=parse_uint,
        default="1",
        help="chain ID of the bundle (default: %(default)s, Ethereum mainnet)",
    )
    parser.add_argument(
        "--token",
        type=parse_address,
        default=SAFE_TOKEN,
        help="bond token (default: %(default)s, SAFE)",
    )
    parser.add_argument(
        "--amount",
        type=parse_uint,
        default=BOND_AMOUNT,
        help="bond amount in the token's smallest unit (default: %(default)s)",
    )
    parser.add_argument(
        "--lockup",
        type=parse_uint,
        default=LOCKUP,
        help="lockup period in seconds (default: %(default)s, 30 days)",
    )
    parser.add_argument(
        "--create2-salt",
        type=parse_bytes32,
        default=CREATE2_SALT,
        help="CREATE2 salt of the deployment, 0x followed by 64 hex digits "
        "(default: %(default)s)",
    )
    return parser


def parse_uint(value):
    """
    An `argparse` type for `uint256` values. Scientific notation such as
    `1337e18` is parsed exactly (without going through a float), and values
    that are not whole numbers are rejected.
    """
    try:
        number = Decimal(value)
    except InvalidOperation:
        number = None
    # `adjusted()` bounds the exponent before `int()`, so that `1e999999999`
    # is rejected instead of building a huge integer.
    if (
        number is None
        or not number.is_finite()
        or number != number.to_integral_value()
        or number < 0
        or number.adjusted() > 78
        or int(number) >= 2**256
    ):
        raise argparse.ArgumentTypeError(f"not a uint256: {value}")
    return int(number)


def parse_address(value):
    """
    An `argparse` type for addresses, returned checksummed. Mixed-case
    addresses must have a valid EIP-55 checksum.
    """
    digits = value[2:]
    if not is_hex_address(value) or (
        digits not in (digits.lower(), digits.upper())
        and not is_checksum_address(value)
    ):
        raise argparse.ArgumentTypeError(f"invalid address: {value}")
    return to_checksum_address(value)


def parse_bytes32(value):
    """
    An `argparse` type for `bytes32` values such as bond IDs and `CREATE2`
    salts: `0x` followed by exactly 64 hex digits.
    """
    digits = value[2:]
    if (
        not value.startswith("0x")
        or len(digits) != 64
        or not all(char in string.hexdigits for char in digits)
    ):
        raise argparse.ArgumentTypeError(f"not 32 bytes of hex: {value}")
    return bytes.fromhex(digits)


class Compiled(NamedTuple):
    abi: list
    bytecode: str


@functools.cache
def compile_bond():
    """The ABI and deployment bytecode of `contracts/BountyBond.vy`."""
    output = vyper.compile_code(
        CONTRACT.read_text(),
        contract_path=CONTRACT,
        output_formats=["abi", "bytecode"],
    )
    return Compiled(output["abi"], output["bytecode"])



def transaction_bundle(chain_id, transactions, created_at=None, safe=None):
    """
    A Safe Transaction Builder bundle, the JSON file that the Transaction
    Builder imports, for `transactions` on chain `chain_id`, created at
    `created_at` (milliseconds since the Unix epoch, default now).

    Each transaction is a dict with `to`, an optional `value` (a decimal
    string, default "0"), and either raw `data` or a `contractMethod` (an ABI
    function fragment) with its `contractInputsValues`, which the Transaction
    Builder shows decoded. `safe`, when given, is recorded as the Safe the
    bundle was created for.
    """
    for tx in transactions:
        if "data" in tx and "contractMethod" in tx:
            raise ValueError("a transaction has either data or a contractMethod")
    if created_at is None:
        created_at = time.time_ns() // 1_000_000
    return {
        "version": "1.0",
        "chainId": str(chain_id),
        "createdAt": created_at,
        "meta": {} if safe is None else {"createdFromSafeAddress": safe},
        "transactions": [
            {
                "to": tx["to"],
                "value": tx.get("value", "0"),
                "data": tx.get("data"),
                "contractMethod": tx.get("contractMethod"),
                "contractInputsValues": tx.get("contractInputsValues"),
            }
            for tx in transactions
        ],
    }


def write_transaction_bundle(path, chain_id, transactions, created_at=None, safe=None):
    """
    Writes the `transaction_bundle` of `transactions` to `path` (creating its
    directory) and returns the path. The JSON has sorted keys, tab indentation
    and a trailing newline.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = transaction_bundle(chain_id, transactions, created_at, safe)
    path.write_text(json.dumps(bundle, indent="\t", sort_keys=True) + "\n")
    return path


def init_code(token, amount, lockup):
    """The `BountyBond` bytecode followed by its ABI-encoded constructor arguments."""
    arguments = encode(["address", "uint256", "uint256"], [token, amount, lockup])
    return HexBytes(compile_bond().bytecode) + arguments


def create2_address(salt, init_code):
    """The address at which the factory deploys `init_code` with `salt`."""
    preimage = b"\xff" + HexBytes(FACTORY) + salt + keccak(init_code)
    return to_checksum_address(keccak(preimage)[12:])


def bond_address(args):
    """
    The address of the `BountyBond` deployed through the factory with the
    deployment parameters of `parser` arguments.
    """
    code = init_code(args.token, args.amount, args.lockup)
    return create2_address(args.create2_salt, code)


def contract_method(abi, name):
    """
    The Transaction Builder `contractMethod` of function `name` in `abi`: its
    inputs, name and whether it is payable.
    """
    [fragment] = [f for f in abi if f["type"] == "function" and f["name"] == name]
    return {
        "inputs": [
            {
                "internalType": param.get("internalType", param["type"]),
                "name": param["name"],
                "type": param["type"],
            }
            for param in fragment["inputs"]
        ],
        "name": name,
        "payable": fragment["stateMutability"] == "payable",
    }


# The normalization rules for submissions. The bond's submission hash is
# computed from the normalized email and subject, so the pipeline that checks
# bonds must apply exactly the same rules. Trimming removes ASCII whitespace
# (`string.whitespace`) only.


def normalize_email(email):
    """The normalized email: trimmed and lowercased."""
    email = email.strip(string.whitespace).lower()
    if not email:
        raise ValueError("the email is empty")
    return email


def normalize_subject(subject):
    """
    The normalized subject: trimmed and otherwise unchanged. It must be plain
    printable ASCII (no tabs, newlines or other control characters).
    """
    subject = subject.strip(string.whitespace)
    if not subject:
        raise ValueError("the subject is empty")
    for char in subject:
        if not " " <= char <= "~":
            raise ValueError(f"the subject is not printable ASCII: {char!r}")
    return subject


def salt_subject(subject):
    """
    The (normalized) `subject` with ` (0x<8 random hex digits>)` appended, so
    that the submission hash cannot be guessed from the email and subject.
    """
    return f"{subject} (0x{secrets.token_hex(4)})"
