// Property 5a: a bond can always be claimed after its lockup.
//
// A bond is unclaimed when `owner != 0 && unlock != 0` (`claim` sets `unlock`
// to 0 and keeps `owner`). The contract holds enough tokens for every
// unclaimed bond (`solvency`), bonds never change except by being claimed
// (`bondStability`), and so the owner of an unclaimed bond can always claim it
// once `unlock` has passed (`claimAfterLockup`).

import "common/Harness.spec";

use invariant cleanOwner;
use invariant noAllowanceFromBond;

// Ghost copies of every bond's storage, kept in sync by the store hooks below
// (proven by `bondGhosts`). `ghostOwnerWord` is the full storage word of
// `owner`, like Vyper's checks see it.
ghost mapping(bytes32 => uint256) ghostOwnerWord {
    init_state axiom forall bytes32 id. ghostOwnerWord[id] == 0;
}
ghost mapping(bytes32 => uint256) ghostUnlock {
    init_state axiom forall bytes32 id. ghostUnlock[id] == 0;
}

// `unclaimedOf[id]` is `isUnclaimed(...)` of bond `id`'s storage (1 if the
// bond is unclaimed, 0 otherwise), kept up to date by the store hooks below on
// every change to the bond's storage. Like the other ghosts, it only exists to
// support the proofs: the contract keeps no such count.
ghost mapping(bytes32 => mathint) unclaimedOf {
    init_state axiom forall bytes32 id. unclaimedOf[id] == 0;
    // The prover does not derive this from the axiom above (without it,
    // `solvency`'s induction base fails).
    init_state axiom (usum bytes32 id. unclaimedOf[id]) == 0;
}

definition isUnclaimed(uint256 ownerWord, uint256 unlock) returns mathint =
    ownerWord != 0 && unlock != 0 ? 1 : 0;

// The number of unclaimed bonds. With `usum`, the prover knows that it is at
// least any single `unclaimedOf[id]`.
definition unclaimedBonds() returns mathint = usum bytes32 id. unclaimedOf[id];

// The hooks use raw slot patterns: the harness's storage variable is labelled
// `BountyBond.bonds` (the module's name is part of it), which CVL cannot name.
// `bonds` is the only storage variable, at slot 0; `owner` is the first word
// of the `Bond` struct and `unlock` the second (byte offset 32). Typing the
// owner hook as `uint256` also gives the full storage word.
hook Sstore (slot 0)[KEY bytes32 id].(offset 0) uint256 newOwnerWord {
    ghostOwnerWord[id] = newOwnerWord;
    unclaimedOf[id] = isUnclaimed(newOwnerWord, ghostUnlock[id]);
}

hook Sstore (slot 0)[KEY bytes32 id].(offset 32) uint256 newUnlock {
    ghostUnlock[id] = newUnlock;
    unclaimedOf[id] = isUnclaimed(ghostOwnerWord[id], newUnlock);
}

// The ghosts match storage.
invariant bondGhosts(bytes32 id)
    ghostOwnerWord[id] == ownerWord(id)
        && ghostUnlock[id] == unlockOf(id)
        && unclaimedOf[id] == isUnclaimed(ghostOwnerWord[id], ghostUnlock[id])
    {
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// The contract holds at least `AMOUNT` tokens per unclaimed bond.
invariant solvency()
    to_mathint(token.balanceOf(currentContract)) >= AMOUNT() * unclaimedBonds()
    {
        preserved bond(bytes32 submission) with (env e) {
            requireTokenIsHarness();
            requireInvariant bondGhosts(computeBondId(e.msg.sender, submission));
            // Bonding as the contract itself would move tokens from itself to
            // itself, adding a bond without adding tokens. It has no allowance
            // from itself, so this reverts (unless `AMOUNT` is 0).
            requireInvariant noAllowanceFromBond(currentContract);
        }
        preserved claim(bytes32 id) with (env e) {
            requireTokenIsHarness();
            requireInvariant bondGhosts(id);
        }
        preserved Token.transfer(address to, uint256 amount) with (env e) {
            requireTokenIsHarness();
            // This is a top-level call to the token, and the bond contract
            // (`currentContract`) cannot be the `msg.sender` of a top-level
            // call: it only calls the token from within `bond` and `claim`
            // (checked above, token calls included), and cannot send a
            // transaction of its own.
            require e.msg.sender != currentContract, "the bond contract is not the sender of a top-level call";
        }
        preserved Token.transferFrom(address from, address to, uint256 amount) with (env e) {
            requireTokenIsHarness();
            requireInvariant noAllowanceFromBond(e.msg.sender);
        }
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// An existing bond's `owner` never changes, and its `unlock` only changes to 0
// (when it is claimed).
rule bondStability(method f, env e, calldataarg args, bytes32 id) {
    requireTokenIsHarness();

    address ownerBefore;
    uint256 unlockBefore;
    ownerBefore, unlockBefore = bonds(id);
    require ownerBefore != 0, "the bond exists";

    f(e, args);

    address ownerAfter;
    uint256 unlockAfter;
    ownerAfter, unlockAfter = bonds(id);
    assert ownerAfter == ownerBefore, "owner never changes";
    assert unlockAfter == unlockBefore || unlockAfter == 0, "unlock only changes to 0";
}

// The bond contract never owns a bond (when `AMOUNT > 0`): bonding as itself
// would pull `AMOUNT` from itself with `transferFrom`, and nobody, itself
// included, has an allowance for its tokens. With `AMOUNT == 0`, `claim` moves
// no tokens, so `claimAfterLockup`'s balance checks hold either way.
invariant noBondOwnedByContract(bytes32 id)
    AMOUNT() > 0 => to_mathint(ownerWord(id)) != to_mathint(currentContract)
    {
        preserved bond(bytes32 submission) with (env e) {
            requireTokenIsHarness();
            requireInvariant noAllowanceFromBond(currentContract);
        }
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// The owner of an unclaimed bond can always claim it once `unlock` has passed,
// and the claim marks the bond claimed and moves exactly `AMOUNT` from the
// contract to the owner.
rule claimAfterLockup(env e, bytes32 id) {
    requireTokenIsHarness();

    address owner;
    uint256 unlock;
    owner, unlock = bonds(id);
    // The precondition of the property: the bond exists and is unclaimed.
    require owner != 0 && unlock != 0, "the bond exists and is unclaimed";
    // The precondition of the property: its owner claims it.
    require e.msg.sender == owner, "the owner claims";
    // The precondition of the property: the lockup has passed.
    require e.block.timestamp >= unlock, "the lockup has passed";
    // `claim` is not payable.
    require e.msg.value == 0, "no value sent";

    // Vyper's owner checks compare the full storage word, which may have
    // dirty bits above the 160 address bits that CVL cannot see.
    requireInvariant cleanOwner(id);
    // Links this bond to the ghost count of unclaimed bonds in `solvency`.
    requireInvariant bondGhosts(id);
    // The contract holds `AMOUNT` for this bond.
    requireInvariant solvency();
    // The owner is not the contract, so the balance checks below are about
    // two different accounts (or `AMOUNT` is 0 and no tokens move).
    requireInvariant noBondOwnedByContract(id);
    // The owner's balance cannot overflow when it receives `AMOUNT` from the
    // contract.
    requireBalancesWithinSupply(owner, currentContract);

    uint256 ownerBefore = token.balanceOf(owner);
    uint256 contractBefore = token.balanceOf(currentContract);

    claim@withrevert(e, id);
    assert !lastReverted, "claim reverted";

    address ownerAfter;
    uint256 unlockAfter;
    ownerAfter, unlockAfter = bonds(id);
    assert ownerAfter == owner, "owner is kept";
    assert unlockAfter == 0, "the bond is claimed";
    assert token.balanceOf(owner) == ownerBefore + AMOUNT(), "owner got AMOUNT";
    assert token.balanceOf(currentContract) == contractBefore - AMOUNT(), "contract paid AMOUNT";
}
