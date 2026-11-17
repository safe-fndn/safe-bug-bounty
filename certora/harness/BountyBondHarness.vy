# pragma version ~=0.4.3
"""
@title Prover BountyBond Harness
@license LGPL-3.0-only
@notice `BountyBond` with extra views for the Certora Prover. Its behaviour,
        storage and immutables are exactly those of `BountyBond`.
"""

from ethereum.ercs import IERC20

# Imported by its path from the repository root (where `certoraRun` runs)
# rather than through a `-p contracts` search path: certora-cli runs
# `vyper -f layout` without search paths, and without the storage layout the
# prover does not know that Vyper hashes mapping slots differently from
# Solidity, which the specs' raw-slot storage hooks rely on.
import contracts.BountyBond as BountyBond

initializes: BountyBond
exports: BountyBond.__interface__


@deploy
def __init__(token: IERC20, amount: uint256, lockup: uint256):
    BountyBond.__init__(token, amount, lockup)


@view
@external
def ownerWord(bond_id: bytes32) -> uint256:
    """
    @notice The full storage word of `bonds[bond_id].owner`. Vyper does not
            clean values on load, so this includes any bits above the 160
            address bits.
    @dev A view instead of a CVL storage access: Certora types this field as
         `address`, so it cannot see the high bits.
    """
    return convert(BountyBond.bonds[bond_id].owner, uint256)


@view
@external
def unlockOf(bond_id: bytes32) -> uint256:
    """
    @notice `bonds[bond_id].unlock`, as a single value that CVL invariants can
            use (they cannot destructure the `bonds` getter's tuple).
    """
    return BountyBond.bonds[bond_id].unlock

