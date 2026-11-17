# pragma version ~=0.4.3
"""
@title Prover ERC20 Token
@notice Well-behaved ERC20 that the Certora Prover links as `BountyBond.TOKEN`.
        No minting, burning, pausing, fees or hooks: `transfer` and
        `transferFrom` either move exactly `amount` and return `True`, or
        revert. Its storage starts in an arbitrary state, like any contract in
        the prover, so specs that reason about balances must constrain them
        (for example, that they sum to at most `totalSupply`).
"""

from ethereum.ercs import IERC20

implements: IERC20


event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256


event Approval:
    owner: indexed(address)
    spender: indexed(address)
    value: uint256


balanceOf: public(HashMap[address, uint256])
allowance: public(HashMap[address, HashMap[address, uint256]])
totalSupply: public(uint256)


@external
def transfer(receiver: address, amount: uint256) -> bool:
    self._transfer(msg.sender, receiver, amount)
    return True


@external
def transferFrom(sender: address, receiver: address, amount: uint256) -> bool:
    self.allowance[sender][msg.sender] -= amount
    self._transfer(sender, receiver, amount)
    return True


@external
def approve(spender: address, amount: uint256) -> bool:
    self.allowance[msg.sender][spender] = amount
    log Approval(owner=msg.sender, spender=spender, value=amount)
    return True


@internal
def _transfer(sender: address, receiver: address, amount: uint256):
    self.balanceOf[sender] -= amount
    self.balanceOf[receiver] += amount
    log Transfer(sender=sender, receiver=receiver, value=amount)
