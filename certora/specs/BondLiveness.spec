// Property 5c, bond liveness: bonds for new submissions cannot be censored.
//
// Anyone who holds and has approved `AMOUNT` can always bond a new (unused)
// submission: no other user and no state of the contract can block it.

import "common/Harness.spec";

use invariant cleanOwner;

// From any state, `bond` for an unused bond ID never reverts when the sender
// holds and has approved `AMOUNT`. It returns that ID, stores the bond for the
// sender with `unlock = timestamp + LOCKUP`, and moves exactly `AMOUNT` from
// the sender to the contract.
rule bondLiveness(env e, bytes32 submission) {
    requireTokenIsHarness();

    address sender = e.msg.sender;
    // The ID `bond` will compute; checked against its return value below.
    bytes32 id = computeBondId(sender, submission);

    address ownerBefore;
    uint256 unlockBefore;
    ownerBefore, unlockBefore = bonds(id);
    // The property is about a new submission, so its bond ID is unused.
    require ownerBefore == 0, "the bond ID is unused";
    // Vyper's "bond exists" check compares the full storage word, which may
    // have dirty bits above the 160 address bits that CVL cannot see.
    requireInvariant cleanOwner(id);

    // `bond` is not payable.
    require e.msg.value == 0, "no value sent";
    // The bond contract cannot be the `msg.sender` of a top-level call: it
    // never calls itself and cannot send a transaction of its own.
    require sender != currentContract, "sender is not the bond contract";
    // The precondition of the property: the sender approved `AMOUNT`.
    require token.allowance(sender, currentContract) >= AMOUNT(), "sender approved AMOUNT";
    // The precondition of the property: the sender holds `AMOUNT`.
    require token.balanceOf(sender) >= AMOUNT(), "sender holds AMOUNT";
    // Real timestamps and the lockup (30 days) are far below 2^256.
    require e.block.timestamp + LOCKUP() <= max_uint256, "unlock does not overflow";
    // The contract's balance cannot overflow when it receives `AMOUNT`.
    requireBalancesWithinSupply(sender, currentContract);

    uint256 senderBefore = token.balanceOf(sender);
    uint256 contractBefore = token.balanceOf(currentContract);

    // CVL warns that `bondId` is undefined if `bond` reverts. It is only used
    // after the `!lastReverted` assert, so only on paths where it is defined.
    bytes32 bondId = bond@withrevert(e, submission);
    assert !lastReverted, "bond reverted";
    assert bondId == id, "bond returned the expected ID";

    address owner;
    uint256 unlock;
    owner, unlock = bonds(bondId);
    assert owner == sender, "owner is the sender";
    assert unlock == e.block.timestamp + LOCKUP(), "unlock is after the lockup";
    assert token.balanceOf(sender) == senderBefore - AMOUNT(), "sender paid AMOUNT";
    assert token.balanceOf(currentContract) == contractBefore + AMOUNT(), "contract got AMOUNT";
}
