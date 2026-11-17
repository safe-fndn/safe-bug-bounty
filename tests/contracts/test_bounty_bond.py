import boa
import pytest
from eth_abi import encode
from eth_account.messages import encode_typed_data
from eth_utils import keccak

# EIP-712 type strings, as in `contracts/BountyBond.vy`.
DOMAIN_TYPE = "EIP712Domain(uint256 chainId,address verifyingContract)"
SUBMISSION_TYPE = "Submission(string email,string subject)"
BOND_TYPE = "Bond(address owner,Submission submission)" + SUBMISSION_TYPE

EMAIL = "alice@example.com"
SUBJECT = "Reentrancy in Vault.withdraw (0x1a2b3c4d)"


def submission_hash(email, subject):
    """The `Submission` struct hash that submitters compute off-chain."""
    return keccak(
        encode(
            ["bytes32", "bytes32", "bytes32"],
            [keccak(text=SUBMISSION_TYPE), keccak(text=email), keccak(text=subject)],
        )
    )


def domain_separator(chain_id, contract):
    return keccak(
        encode(
            ["bytes32", "uint256", "address"],
            [keccak(text=DOMAIN_TYPE), chain_id, str(contract)],
        )
    )


def bond_id(chain_id, contract, owner, submission):
    """The EIP-712 hash of `Bond{owner, submission}`, i.e. the bond ID."""
    struct_hash = keccak(
        encode(
            ["bytes32", "address", "bytes32"],
            [keccak(text=BOND_TYPE), str(owner), submission],
        )
    )
    return keccak(b"\x19\x01" + domain_separator(chain_id, contract) + struct_hash)


@pytest.fixture
def chain_id():
    return boa.env.evm.patch.chain_id


@pytest.fixture
def submission():
    return submission_hash(EMAIL, SUBJECT)


@pytest.fixture
def post_bond(token, amount):
    """Approves `AMOUNT` and bonds `submission` as `sender`."""

    def post_bond(contract, sender, submission):
        with boa.env.prank(sender):
            token.approve(contract, amount)
            return contract.bond(submission)

    return post_bond


@pytest.fixture
def bonded(bond, alice, submission, post_bond):
    """Alice's bond ID for `submission`."""
    return post_bond(bond, alice, submission)


def events(contract, name):
    """The `name` events of the contract's last call (views count as calls)."""
    logs = contract.get_logs(include_child_logs=False)
    return [log for log in logs if type(log).__name__ == name]


def test_deploy(bond, token, amount, lockup):
    assert bond.TOKEN() == token.address
    assert bond.AMOUNT() == amount
    assert bond.LOCKUP() == lockup


def test_domain_separator(bond, chain_id):
    assert bond.domainSeparator() == domain_separator(chain_id, bond.address)


def test_bond_id(bond, alice, chain_id, bonded):
    submission = submission_hash(EMAIL, SUBJECT)
    assert bonded == bond_id(chain_id, bond.address, alice, submission)
    assert bonded == bond.computeBondId(alice, submission)

    # The same ID from eth_account's EIP-712 implementation, which hashes the
    # nested `Submission` struct from the email and subject itself.
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
                "Submission": [
                    {"name": "email", "type": "string"},
                    {"name": "subject", "type": "string"},
                ],
            },
            "primaryType": "Bond",
            "domain": {"chainId": chain_id, "verifyingContract": str(bond.address)},
            "message": {
                "owner": str(alice),
                "submission": {"email": EMAIL, "subject": SUBJECT},
            },
        }
    )
    assert message.header == bond.domainSeparator()
    assert bonded == keccak(b"\x19" + message.version + message.header + message.body)


def test_bond(
    bond, token, alice, amount, lockup, initial_balance, submission, bonded
):
    unlock = boa.env.timestamp + lockup
    [event] = events(bond, "Bonded")
    assert (event.bond_id, event.owner, event.submission, event.unlock) == (
        bonded,
        alice,
        submission,
        unlock,
    )

    assert bond.bonds(bonded) == (alice, unlock)
    assert token.balanceOf(alice) == initial_balance - amount
    assert token.balanceOf(bond) == amount


def test_bond_twice(bond, alice, submission, post_bond, bonded):
    with boa.reverts("bond exists"):
        post_bond(bond, alice, submission)


def test_bond_different_senders(
    bond, token, bob, amount, submission, post_bond, bonded
):
    other = post_bond(bond, bob, submission)
    assert other != bonded
    assert bond.bonds(other).owner == bob
    assert token.balanceOf(bond) == 2 * amount


def test_bond_different_deployments(
    bond, token, alice, amount, lockup, submission, post_bond, bonded
):
    other = bond.deployer.deploy(token, amount, lockup)
    assert post_bond(other, alice, submission) != bonded


def test_bond_insufficient_allowance(bond, token, alice, amount, submission):
    with boa.env.prank(alice):
        token.approve(bond, amount - 1)
        # The mock token reverts with an underflow, so `bond` sees a failed call.
        with boa.reverts(compiler="external call failed"):
            bond.bond(submission)


def test_bond_insufficient_balance(
    bond, token, alice, bob, amount, initial_balance, submission
):
    with boa.env.prank(alice):
        token.transfer(bob, initial_balance - amount + 1)
        token.approve(bond, amount)
        with boa.reverts(compiler="external call failed"):
            bond.bond(submission)


def test_claim_lockup(bond, token, alice, initial_balance, bonded):
    unlock = bond.bonds(bonded).unlock
    boa.env.time_travel(seconds=unlock - 1 - boa.env.timestamp)
    with boa.env.prank(alice), boa.reverts("locked"):
        bond.claim(bonded)

    boa.env.time_travel(seconds=1)
    assert boa.env.timestamp == unlock
    with boa.env.prank(alice):
        bond.claim(bonded)

    [event] = events(bond, "Claimed")
    assert (event.bond_id, event.owner) == (bonded, alice)
    assert bond.bonds(bonded) == (alice, 0)
    assert token.balanceOf(alice) == initial_balance
    assert token.balanceOf(bond) == 0


def test_claim_not_owner(bond, bob, lockup, bonded):
    boa.env.time_travel(seconds=lockup)
    with boa.env.prank(bob), boa.reverts("not owner"):
        bond.claim(bonded)


def test_claim_unknown_bond(bond, alice, submission):
    with boa.env.prank(alice), boa.reverts("unknown bond"):
        bond.claim(submission)


def test_claim_twice(bond, alice, lockup, bonded):
    boa.env.time_travel(seconds=lockup)
    with boa.env.prank(alice):
        bond.claim(bonded)
        with boa.reverts("already claimed"):
            bond.claim(bonded)


def test_bond_after_claim(bond, alice, lockup, submission, post_bond, bonded):
    boa.env.time_travel(seconds=lockup)
    with boa.env.prank(alice):
        bond.claim(bonded)
    with boa.reverts("bond exists"):
        post_bond(bond, alice, submission)


@pytest.mark.parametrize("lockup", [0])
def test_no_lockup(bond, alice, bonded):
    # A fresh bond has `unlock = block.timestamp`, which is not 0 ("claimed").
    assert bond.bonds(bonded) == (alice, boa.env.timestamp)
    with boa.env.prank(alice):
        bond.claim(bonded)
    assert bond.bonds(bonded) == (alice, 0)


def test_transfer_failed(bond, false_token, alice, amount, lockup, submission):
    bond = bond.deployer.deploy(false_token, amount, lockup)
    with boa.env.prank(alice):
        with boa.reverts("transfer failed"):
            bond.bond(submission)

        false_token.set_succeed(True)
        bonded = bond.bond(submission)
        false_token.set_succeed(False)
        boa.env.time_travel(seconds=lockup)
        with boa.reverts("transfer failed"):
            bond.claim(bonded)


def test_compute_submission_hash(bond):
    assert bond.computeSubmissionHash(EMAIL, SUBJECT) == submission_hash(EMAIL, SUBJECT)


def test_invalid_inputs(bond):
    # Inputs are hashed as given (normalizing them is the caller's job), so the
    # only invalid ones are longer than the view's limits (256 bytes for the
    # email, 1024 for the subject), which the ABI decoder rejects.
    for email, subject in [("a" * 257, SUBJECT), (EMAIL, "a" * 1025)]:
        with boa.reverts():
            bond.computeSubmissionHash(email, subject)
