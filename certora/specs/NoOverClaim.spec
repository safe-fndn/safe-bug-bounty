// Property 5b: nobody can claim more tokens than they locked.
//
// `bonded[a]` and `claimed[a]` are the tokens that `a` has bonded and claimed
// back. A bond adds `AMOUNT` to `bonded[owner]` when it is created (its `owner`
// goes from 0 to the sender), and to `claimed[owner]` when it is claimed (its
// `unlock` goes from non-zero to 0, while `owner` stays set). `noOverClaim`
// proves `claimed[a] <= bonded[a]`, and `balanceDecrease` proves that tokens
// only leave the contract when a bond is claimed, at most `AMOUNT` per call,
// and to that bond's owner.

import "common/Harness.spec";

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

// Tokens bonded and claimed back per owner. The keys are `mathint` so that
// both the hooks' `uint256` storage words and the invariants' `address`es can
// index them (CVL converts neither type to the other).
ghost mapping(mathint => mathint) bonded {
    init_state axiom forall mathint a. bonded[a] == 0;
}
ghost mapping(mathint => mathint) claimed {
    init_state axiom forall mathint a. claimed[a] == 0;
}

// `unclaimedOf[a][id]` is 1 if `a` owns bond `id` and it is unclaimed, 0
// otherwise (proven by `unclaimedGhosts`).
ghost mapping(mathint => mapping(bytes32 => mathint)) unclaimedOf {
    init_state axiom forall mathint a. forall bytes32 id. unclaimedOf[a][id] == 0;
    // The prover does not derive this from the axiom above (as in
    // `ClaimAfterLockup.spec`).
    init_state axiom forall mathint a. (usum bytes32 id. unclaimedOf[a][id]) == 0;
}

// The bonds that flip to claimed in a call, and the last one of them, for
// `balanceDecrease` (which resets `flips` before the call).
ghost mathint flips;
ghost bytes32 flippedId;

definition isUnclaimedOf(mathint a, uint256 ownerWord, uint256 unlock) returns mathint =
    a != 0 && to_mathint(ownerWord) == a && unlock != 0 ? 1 : 0;

// The number of unclaimed bonds that `a` owns.
definition unclaimedBonds(mathint a) returns mathint = usum bytes32 id. unclaimedOf[a][id];

// The hooks use raw slot patterns: the harness's storage variable is labelled
// `BountyBond.bonds` (the module's name is part of it), which CVL cannot name.
// `bonds` is the only storage variable, at slot 0; `owner` is the first word
// of the `Bond` struct and `unlock` the second (byte offset 32). Typing the
// owner hook as `uint256` also gives the full storage word.
//
// `unclaimedOf` is updated from the ghosts alone (the previous owner is
// `ghostOwnerWord[id]`, not the hook's old storage value), so that
// `unclaimedGhosts` holds without assuming `bondGhosts`.
hook Sstore (slot 0)[KEY bytes32 id].(offset 0) uint256 newOwnerWord (uint256 oldOwnerWord) {
    uint256 previousOwnerWord = ghostOwnerWord[id];
    ghostOwnerWord[id] = newOwnerWord;
    // A bond is created.
    if (oldOwnerWord == 0 && newOwnerWord != 0) {
        bonded[newOwnerWord] = bonded[newOwnerWord] + AMOUNT();
    }
    unclaimedOf[previousOwnerWord][id] = isUnclaimedOf(previousOwnerWord, newOwnerWord, ghostUnlock[id]);
    unclaimedOf[newOwnerWord][id] = isUnclaimedOf(newOwnerWord, newOwnerWord, ghostUnlock[id]);
}

hook Sstore (slot 0)[KEY bytes32 id].(offset 32) uint256 newUnlock (uint256 oldUnlock) {
    uint256 ownerWord = ghostOwnerWord[id];
    ghostUnlock[id] = newUnlock;
    // A bond flips to claimed.
    if (oldUnlock != 0 && newUnlock == 0) {
        flips = flips + 1;
        flippedId = id;
        if (ownerWord != 0) {
            claimed[ownerWord] = claimed[ownerWord] + AMOUNT();
        }
    }
    unclaimedOf[ownerWord][id] = isUnclaimedOf(ownerWord, ownerWord, newUnlock);
}

// The storage ghosts match storage.
invariant bondGhosts(bytes32 id)
    ghostOwnerWord[id] == ownerWord(id) && ghostUnlock[id] == unlockOf(id)
    {
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// `unclaimedOf` matches the storage ghosts.
invariant unclaimedGhosts(address a, bytes32 id)
    unclaimedOf[to_mathint(a)][id] == isUnclaimedOf(to_mathint(a), ghostOwnerWord[id], ghostUnlock[id])
    {
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// Every token that `a` has bonded is either claimed back or still locked in an
// unclaimed bond of `a` (or, for a bond created with `unlock == 0`, which needs
// `block.timestamp == 0`, in neither).
invariant accounting(address a)
    bonded[to_mathint(a)] >= claimed[to_mathint(a)] + AMOUNT() * unclaimedBonds(to_mathint(a))
    {
        preserved bond(bytes32 submission) with (env e) {
            requireTokenIsHarness();
            bytes32 id = computeBondId(e.msg.sender, submission);
            requireInvariant bondGhosts(id);
            requireInvariant unclaimedGhosts(a, id);
        }
        preserved claim(bytes32 id) with (env e) {
            requireTokenIsHarness();
            requireInvariant bondGhosts(id);
            requireInvariant unclaimedGhosts(a, id);
        }
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// Nobody claims back more tokens than they bonded.
invariant noOverClaim(address a)
    claimed[to_mathint(a)] <= bonded[to_mathint(a)]
    {
        preserved bond(bytes32 submission) with (env e) {
            requireTokenIsHarness();
            bytes32 id = computeBondId(e.msg.sender, submission);
            requireInvariant bondGhosts(id);
            requireInvariant unclaimedGhosts(a, id);
            requireInvariant accounting(a);
        }
        preserved claim(bytes32 id) with (env e) {
            requireTokenIsHarness();
            requireInvariant bondGhosts(id);
            requireInvariant unclaimedGhosts(a, id);
            requireInvariant accounting(a);
        }
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// For any call, the contract's token balance decreases by at most `AMOUNT`,
// and only when exactly one bond flips to claimed, with the tokens going to
// that bond's owner (any `o` that is the owner receives all of them).
rule balanceDecrease(method f, env e, calldataarg args, address o) {
    requireTokenIsHarness();
    // Only `transferFrom`s by a spender with an allowance from the contract
    // could move its tokens otherwise.
    requireInvariant noAllowanceFromBond(e.msg.sender);
    // The bond contract (`currentContract`) cannot be the `msg.sender` of a
    // top-level call such as `Token.transfer`: it only calls the token from
    // within `bond` and `claim`, and cannot send a transaction of its own.
    require e.msg.sender != currentContract, "the bond contract is not the sender of a top-level call";

    uint256 balanceBefore = token.balanceOf(currentContract);
    uint256 ownerBalanceBefore = token.balanceOf(o);
    flips = 0;

    f(e, args);

    mathint decrease = balanceBefore - token.balanceOf(currentContract);
    address owner;
    uint256 unlock;
    owner, unlock = bonds(flippedId);

    assert decrease <= to_mathint(AMOUNT()), "decreases by at most AMOUNT";
    assert decrease > 0 => flips == 1, "decreases only when exactly one bond flips to claimed";
    assert decrease > 0 && owner == o => token.balanceOf(o) == ownerBalanceBefore + decrease,
        "the tokens go to the owner of the claimed bond";
}
