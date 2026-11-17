# pragma version ~=0.4.3
"""
@title Bounty Bond
@notice Locks a fixed token amount per bug bounty submission. The owner can
        claim it back once the lockup period has passed.
"""

from ethereum.ercs import IERC20


DOMAIN_TYPEHASH: constant(bytes32) = keccak256(
    "EIP712Domain(uint256 chainId,address verifyingContract)"
)
SUBMISSION_TYPEHASH: constant(bytes32) = keccak256(
    "Submission(string email,string subject)"
)
BOND_TYPEHASH: constant(bytes32) = keccak256(
    "Bond(address owner,Submission submission)Submission(string email,string subject)"
)

# Maximum lengths (in bytes) of the email and subject that the convenience
# view `computeSubmissionHash` accepts. `bond` itself only sees the submission
# hash, so it has no such limit.
MAX_EMAIL_LENGTH: constant(uint256) = 256
MAX_SUBJECT_LENGTH: constant(uint256) = 1024


# A claimed bond keeps its owner (so its ID cannot be bonded again) and has
# `unlock` set to 0. A fresh bond never has `unlock == 0`, because
# `block.timestamp` is never 0 after genesis.
struct Bond:
    owner: address
    # Timestamp from which the bond can be claimed, 0 once claimed.
    unlock: uint256


event Bonded:
    bond_id: indexed(bytes32)
    owner: indexed(address)
    submission: indexed(bytes32)
    unlock: uint256


event Claimed:
    bond_id: indexed(bytes32)
    owner: indexed(address)


# Only standard ERC20 tokens are supported: `transfer` and `transferFrom` must
# return `True` if and only if the full amount was moved (no missing return
# values, no fee-on-transfer).
TOKEN: public(immutable(IERC20))
AMOUNT: public(immutable(uint256))
LOCKUP: public(immutable(uint256))

bonds: public(HashMap[bytes32, Bond])


@deploy
def __init__(token: IERC20, amount: uint256, lockup: uint256):
    TOKEN = token
    AMOUNT = amount
    LOCKUP = lockup


@view
@external
def domainSeparator() -> bytes32:
    """
    @notice The EIP-712 domain separator for bond IDs.
    """
    return self._domain_separator()


@external
def bond(submission: bytes32) -> bytes32:
    """
    @notice Locks `AMOUNT` tokens from the sender for `LOCKUP` seconds.
    @dev `submission` is the EIP-712 struct hash of
           Submission(string email,string subject)
         computed off-chain as
           keccak256(abi.encode(
               keccak256("Submission(string email,string subject)"),
               keccak256(bytes(email)),
               keccak256(bytes(subject))
           ))
         so that the submitter's email and subject never appear on-chain.
         They may be guessable, so append random text to the subject for
         extra entropy (the bond script does this unless `--no-salt`).
    @param submission The `Submission` struct hash.
    @return The bond ID, the EIP-712 typed-data hash
              keccak256(0x1901 ++ domainSeparator() ++ hashStruct(Bond))
            of `Bond(address owner,Submission submission)` with
            `owner = msg.sender`, in the domain
            `EIP712Domain(uint256 chainId,address verifyingContract)`.
    """
    bond_id: bytes32 = self._bond_id(msg.sender, submission)
    assert self.bonds[bond_id].owner == empty(address), "bond exists"

    unlock: uint256 = block.timestamp + LOCKUP
    self.bonds[bond_id] = Bond(owner=msg.sender, unlock=unlock)
    assert extcall TOKEN.transferFrom(msg.sender, self, AMOUNT), "transfer failed"

    log Bonded(
        bond_id=bond_id, owner=msg.sender, submission=submission, unlock=unlock
    )
    return bond_id


@external
def claim(bond_id: bytes32):
    """
    @notice Returns the bonded tokens to the owner once the lockup has passed.
    @dev Reverts unless the bond exists, the sender owns it, it has not been
         claimed yet and its lockup has passed (checked in that order).
    @param bond_id The ID returned by `bond`.
    """
    owner: address = self.bonds[bond_id].owner
    unlock: uint256 = self.bonds[bond_id].unlock
    assert owner != empty(address), "unknown bond"
    assert msg.sender == owner, "not owner"
    assert unlock != 0, "already claimed"
    assert block.timestamp >= unlock, "locked"

    self.bonds[bond_id].unlock = 0
    assert extcall TOKEN.transfer(owner, AMOUNT), "transfer failed"

    log Claimed(bond_id=bond_id, owner=owner)


@view
@external
def computeBondId(owner: address, submission: bytes32) -> bytes32:
    """
    @notice The bond ID that `bond(submission)` returns when called by `owner`.
    @param owner The account that posts the bond.
    @param submission The `Submission` struct hash.
    @return The bond ID (see `bond`).
    """
    return self._bond_id(owner, submission)


@pure
@external
def computeSubmissionHash(
    email: String[MAX_EMAIL_LENGTH], subject: String[MAX_SUBJECT_LENGTH]
) -> bytes32:
    """
    @notice View-only function provided for convenience: the `Submission`
            struct hash that `bond` expects.
    @dev Do NOT call this on-chain, or with `eth_call` through an RPC node you
         do not trust: that reveals the email and subject (to everyone
         on-chain, or to the node), which lets others submit using your bond.
         Compute the hash off-chain instead (see `bond`).
         The email and subject must already be normalized, as the bond
         script normalizes them (`normalize_email` and `normalize_subject` in
         `scripts/common.py`): they are hashed exactly as given, and nothing
         is checked here.
    @param email The submitter's (normalized) email.
    @param subject The submission's (normalized and salted) subject.
    @return The `Submission(string email,string subject)` struct hash.
    """
    return self._submission_hash(email, subject)


@view
@internal
def _domain_separator() -> bytes32:
    return keccak256(abi_encode(DOMAIN_TYPEHASH, chain.id, self))


@view
@internal
def _bond_id(owner: address, submission: bytes32) -> bytes32:
    return keccak256(
        concat(
            b"\x19\x01",
            self._domain_separator(),
            keccak256(abi_encode(BOND_TYPEHASH, owner, submission)),
        )
    )


@pure
@internal
def _submission_hash(
    email: String[MAX_EMAIL_LENGTH], subject: String[MAX_SUBJECT_LENGTH]
) -> bytes32:
    return keccak256(
        abi_encode(SUBMISSION_TYPEHASH, keccak256(email), keccak256(subject))
    )
