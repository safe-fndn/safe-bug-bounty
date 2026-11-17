# pragma version ~=0.4.3
"""
@title Mock Failing ERC20 Token
@license LGPL-3.0-only
@notice Transfers move nothing and return `succeed`, which anyone can set.
        Used to test that `BountyBond` checks the returned `bool`.
"""

succeed: public(bool)


@external
def set_succeed(succeed: bool):
    self.succeed = succeed


@external
def transfer(receiver: address, amount: uint256) -> bool:
    return self.succeed


@external
def transferFrom(sender: address, receiver: address, amount: uint256) -> bool:
    return self.succeed
