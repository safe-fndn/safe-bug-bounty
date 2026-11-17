"""
Writes a Safe Transaction Builder bundle that posts a bond for a submission:
it approves the bond amount and calls `bond` on the `BountyBond` contract, with
the Safe as the bond's owner.
"""

from pathlib import Path

from hexbytes import HexBytes

import common


def main(argv=None):
    parser = common.parser("Write a bundle that posts a bond for a submission.")
    parser.add_argument(
        "--owner",
        type=common.parse_address,
        required=True,
        help="the Safe that posts the bond and can claim it back",
    )
    parser.add_argument(
        "--email", required=True, help="the email address of the submission"
    )
    parser.add_argument(
        "--subject", required=True, help="the subject line of the submission"
    )
    parser.add_argument(
        "--no-salt",
        dest="salt",
        action="store_false",
        help="don't append the random ' (0x<8 hex digits>)' to the subject that "
        "keeps the bond from being linked to a guessed email and subject",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="bundle file (default: bundles/bond-<bond ID prefix>.json)",
    )
    args = parser.parse_args(argv)

    try:
        email = common.normalize_email(args.email)
    except ValueError as error:
        parser.error(f"argument --email: {error}")
    try:
        subject = common.normalize_subject(args.subject)
    except ValueError as error:
        parser.error(f"argument --subject: {error}")
    if args.salt:
        subject = common.salt_subject(subject)

    address = common.bond_address(args)
    submission = common.compute_submission_hash(email, subject)
    bond_id = common.compute_bond_id(args.chain_id, address, args.owner, submission)

    # Without a node, the current allowance is unknown, so the bundle always
    # approves the bond amount.
    transactions = [
        {
            "to": args.token,
            "contractMethod": common.contract_method(common.ERC20_ABI, "approve"),
            "contractInputsValues": {"spender": address, "value": str(args.amount)},
        },
        {
            "to": address,
            "contractMethod": common.contract_method(common.compile_bond().abi, "bond"),
            "contractInputsValues": {"submission": HexBytes(submission).to_0x_hex()},
        },
    ]
    out = args.out or Path("bundles") / f"bond-{bond_id.hex()[:8]}.json"
    path = common.write_transaction_bundle(
        out, args.chain_id, transactions, safe=args.owner
    )

    print("Subject (use it verbatim in the submission email):")
    print()
    print(f"    {subject}")
    print()
    if args.salt:
        print("The subject ends in a random salt, which cannot be recovered.")
        print("Keep it: the bond only matches a submission with this exact subject.")
        print()
    print(f"Email:           {email}")
    print(f"Submission hash: {HexBytes(submission).to_0x_hex()}")
    print(f"Bond ID:         {HexBytes(bond_id).to_0x_hex()}")
    print(f"BountyBond:      {address} on chain ID {args.chain_id}")
    print(f"Owner:           {args.owner}")
    print(f"Amount:          {args.amount} of token {args.token}")
    print(
        f"Unlock:          {args.lockup} seconds ({args.lockup / 86400:g} days) "
        "after the bond transaction executes"
    )
    print(f"Transaction bundle: {path}")


if __name__ == "__main__":
    common.run(main)
