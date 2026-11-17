"""
Writes a Safe Transaction Builder bundle that claims a bond back: it calls
`claim` on the `BountyBond` contract, which returns the bond amount to the Safe
that owns the bond.
"""

from pathlib import Path

from hexbytes import HexBytes

import common


def main(argv=None):
    parser = common.parser("Write a bundle that claims a bond back after its lockup.")
    parser.add_argument(
        "--owner",
        type=common.parse_address,
        required=True,
        help="the Safe that owns the bond and claims it",
    )
    parser.add_argument(
        "--bond-id",
        type=common.parse_bytes32,
        required=True,
        help="the bond ID, 0x followed by 64 hex digits",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="bundle file (default: bundles/claim-<bond ID prefix>.json)",
    )
    args = parser.parse_args(argv)

    address = common.bond_address(args)
    bond_id = HexBytes(args.bond_id).to_0x_hex()

    # Without a node, the bond's state is unknown: the Safe UI's simulation
    # shows the contract's revert reason if the claim cannot succeed.
    transactions = [
        {
            "to": address,
            "contractMethod": common.contract_method(
                common.compile_bond().abi, "claim"
            ),
            "contractInputsValues": {"bond_id": bond_id},
        },
    ]
    out = args.out or Path("bundles") / f"claim-{args.bond_id.hex()[:8]}.json"
    path = common.write_transaction_bundle(
        out, args.chain_id, transactions, safe=args.owner
    )

    print(f"Bond ID:         {bond_id}")
    print(f"BountyBond:      {address} on chain ID {args.chain_id}")
    print(f"Owner:           {args.owner}")
    print(f"Amount returned: {args.amount} of token {args.token}")
    print()
    print("The claim only succeeds once the lockup has passed, and only for the")
    print("Safe that owns the bond. Otherwise the Safe UI's simulation shows the")
    print('revert reason ("locked", "not owner", "already claimed" or "unknown bond").')
    print()
    print(f"Transaction bundle: {path}")


if __name__ == "__main__":
    common.run(main)
