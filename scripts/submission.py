"""
Computes the submission hash of a submission email (an `.eml` file, such as
Gmail's "Download message"), and its bond ID when given the bond's owner.
"""

from email import policy
from email.parser import BytesParser
from pathlib import Path

from hexbytes import HexBytes

import common


def read_submission(path):
    """
    The normalized email (the `From` address) and subject of the submission
    email at `path`. Raises a `ScriptError` if the email is not a valid
    submission: it must have exactly one `From` address and one `Subject`, the
    subject must follow the submission rules (`common.normalize_subject`), and
    it must not have attachments or any parts other than text.
    """
    with open(path, "rb") as file:
        message = BytesParser(policy=policy.default).parse(file)

    senders = message.get_all("From", [])
    if len(senders) != 1 or len(senders[0].addresses) != 1:
        raise common.ScriptError("the email must have exactly one From address")
    [sender] = senders[0].addresses
    if not sender.username or not sender.domain:
        raise common.ScriptError(f"invalid From address: {sender}")

    subjects = message.get_all("Subject", [])
    if len(subjects) != 1:
        raise common.ScriptError("the email must have exactly one Subject")

    for part in message.walk():
        if part.is_attachment() or part.get_filename() is not None:
            raise common.ScriptError("the email must not have attachments")
        if part.get_content_maintype() not in ("text", "multipart"):
            raise common.ScriptError(
                f"the email must only have text parts: {part.get_content_type()}"
            )

    try:
        email = common.normalize_email(sender.addr_spec)
        subject = common.normalize_subject(str(subjects[0]))
    except ValueError as error:
        raise common.ScriptError(error) from None
    return email, subject


def main(argv=None):
    parser = common.parser("Compute the submission hash of a submission email.")
    parser.add_argument("eml", type=Path, help="the submission email (.eml file)")
    parser.add_argument(
        "--owner",
        type=common.parse_address,
        help="the Safe that posted the bond, to also compute the bond ID",
    )
    args = parser.parse_args(argv)

    email, subject = read_submission(args.eml)
    submission = common.compute_submission_hash(email, subject)

    print(f"Email:           {email}")
    print(f"Subject:         {subject}")
    print(f"Submission hash: {HexBytes(submission).to_0x_hex()}")
    if args.owner is not None:
        address = common.bond_address(args)
        bond_id = common.compute_bond_id(args.chain_id, address, args.owner, submission)
        print(f"Bond ID:         {HexBytes(bond_id).to_0x_hex()}")
        print(f"BountyBond:      {address} on chain ID {args.chain_id}")
        print(f"Owner:           {args.owner}")


if __name__ == "__main__":
    common.run(main)
