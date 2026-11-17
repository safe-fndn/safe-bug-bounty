// Token model shared by all specs: `BountyBond.TOKEN` is the `Token` harness.
//
// The conf cannot `link` `BountyBond:TOKEN=Token`: certora-cli only finds
// immutables through solc's `immutableReferences`, which Vyper does not emit.
// Instead, `_.transfer`/`_.transferFrom` are summarized with `DISPATCHER(true)`
// so calls to `TOKEN` run the harness, and every rule (and every invariant's
// `preserved` block) must call `requireTokenIsHarness()` so that `TOKEN()` is
// the harness's address.

using Token as token;

methods {
    function TOKEN() external returns (address) envfree;
    function AMOUNT() external returns (uint256) envfree;
    function LOCKUP() external returns (uint256) envfree;

    function token.balanceOf(address) external returns (uint256) envfree;
    function token.allowance(address, address) external returns (uint256) envfree;
    function token.totalSupply() external returns (uint256) envfree;

    function _.transfer(address, uint256) external => DISPATCHER(true);
    function _.transferFrom(address, address, uint256) external => DISPATCHER(true);
}

function requireTokenIsHarness() {
    require TOKEN() == token, "BountyBond.TOKEN is the Token harness";
}

// The harness's storage starts arbitrary, so its balances need not sum to at
// most `totalSupply`, as they do in any real ERC20 (and in the harness, if it
// started empty: it has no mint, and transfers keep the sum). Two distinct
// balances then sum to at most `totalSupply`, so neither overflows when the
// other sends it tokens.
function requireBalancesWithinSupply(address a, address b) {
    require a != b => token.balanceOf(a) + token.balanceOf(b) <= token.totalSupply(),
        "two distinct balances sum to at most totalSupply";
}
