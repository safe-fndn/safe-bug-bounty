// Shared by specs that verify `certora/harness/BountyBondHarness.vy`: its extra
// views and the `cleanOwner` and `noAllowanceFromBond` invariants. Specs that
// `requireInvariant` one of them must also `use invariant <name>;` so that it
// is proven.

import "Token.spec";

methods {
    function bonds(bytes32) external returns (address, uint256) envfree;
    function ownerWord(bytes32) external returns (uint256) envfree;
    function unlockOf(bytes32) external returns (uint256) envfree;
    function computeBondId(address, bytes32) external returns (bytes32) envfree;
}

// A bond's `owner` storage word never has bits set above the 160 address bits.
// The prover starts from arbitrary storage, where it could, and Vyper compares
// the full word (in `bond`'s "bond exists" check and in `claim`'s owner
// checks), while CVL only sees an `address`. Vyper only ever stores clean
// addresses, so this holds.
//
// The word is read through the harness's `ownerWord`: CVL types direct storage
// access to `bonds[id].owner` as `address`, so it cannot see the high bits.
invariant cleanOwner(bytes32 id)
    ownerWord(id) <= max_uint160
    {
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }

// Nobody can move the contract's tokens with `transferFrom`: it never calls
// `approve`.
invariant noAllowanceFromBond(address spender)
    token.allowance(currentContract, spender) == 0
    {
        preserved constructor() {
            // The token harness's storage starts arbitrary. On a real chain,
            // only the contract itself can approve spenders for its address,
            // and it has no code to do so before it is deployed.
            require token.allowance(currentContract, spender) == 0,
                "no allowance from the bond contract when it is deployed";
        }
        preserved Token.approve(address s, uint256 amount) with (env e) {
            requireTokenIsHarness();
            // This is a top-level call to the token, and the bond contract
            // (`currentContract`) cannot be the `msg.sender` of a top-level
            // call: it never calls `approve` (it only calls `transferFrom` and
            // `transfer`, from within `bond` and `claim`), and cannot send a
            // transaction of its own.
            require e.msg.sender != currentContract, "the bond contract is not the sender of a top-level call";
        }
        preserved with (env e) {
            requireTokenIsHarness();
        }
    }
