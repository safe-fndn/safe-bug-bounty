"""
Writes a Safe Transaction Builder bundle that deploys `contracts/BountyBond.vy`
through the Safe singleton factory, and prints the address it will have.
"""

from pathlib import Path

from hexbytes import HexBytes

import common


def main(argv=None):
    parser = common.parser("Write a bundle that deploys the BountyBond contract.")
    parser.add_argument(
        "--out",
        type=Path,
        help="bundle file (default: bundles/deploy-<chain ID>.json)",
    )
    args = parser.parse_args(argv)

    code = common.init_code(args.token, args.amount, args.lockup)
    transaction = {
        "to": common.FACTORY,
        "data": HexBytes(args.create2_salt + code).to_0x_hex(),
    }
    out = args.out or Path("bundles") / f"deploy-{args.chain_id}.json"
    path = common.write_transaction_bundle(out, args.chain_id, [transaction])

    address = common.bond_address(args)
    print(f"BountyBond will be deployed at {address} on chain ID {args.chain_id}")
    print(f"  token:        {args.token}")
    print(f"  amount:       {args.amount}")
    print(f"  lockup:       {args.lockup}")
    print(f"  CREATE2 salt: {HexBytes(args.create2_salt).to_0x_hex()}")
    print(f"Transaction bundle: {path}")


if __name__ == "__main__":
    common.run(main)
