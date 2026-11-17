from email.message import EmailMessage

import pytest
from hexbytes import HexBytes

import bond
import common
import submission

EMAIL = "alice@example.com"
SUBJECT = "Reentrancy in Vault.withdraw"
OWNER = "0x0000000000000000000000000000000000005afe"


def printed(output, label):
    """The value printed after `label:`."""
    return output.split(f"{label}:")[1].split()[0]


def message(sender="Alice <Alice@Example.COM>", subject=SUBJECT, body="Details."):
    """A plain text submission email."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "bounty@example.org"
    message["Subject"] = subject
    message.set_content(body)
    return message


@pytest.fixture
def eml(tmp_path):
    """A function that writes an email (a message or raw bytes) to a file."""

    def write(email):
        path = tmp_path / "submission.eml"
        path.write_bytes(email if isinstance(email, bytes) else bytes(email))
        return path

    return write


def test_read_submission(eml):
    assert submission.read_submission(eml(message())) == (EMAIL, SUBJECT)


def test_read_submission_trims_subject(eml):
    path = eml(message(subject=f"  {SUBJECT} "))
    assert submission.read_submission(path) == (EMAIL, SUBJECT)


def test_read_submission_unfolds_subject(eml):
    raw = (
        f"From: {EMAIL}\r\n"
        "Subject: Reentrancy in Vault.withdraw allows draining\r\n"
        " all deposits\r\n"
        "\r\n"
        "Details.\r\n"
    ).encode()
    _, subject = submission.read_submission(eml(raw))
    assert subject == "Reentrancy in Vault.withdraw allows draining all deposits"


def test_read_submission_multipart_alternative(eml):
    email = message()
    email.add_alternative("<p>Details.</p>", subtype="html")
    assert submission.read_submission(eml(email)) == (EMAIL, SUBJECT)


@pytest.mark.parametrize(
    "sender",
    [
        "",
        "Alice",
        f"{EMAIL}, bob@example.com",
        "Team: alice@example.com, bob@example.com;",
    ],
)
def test_read_submission_rejects_from(eml, sender):
    with pytest.raises(common.ScriptError, match="From"):
        submission.read_submission(eml(message(sender=sender)))


def test_read_submission_rejects_multiple_from(eml):
    raw = f"From: {EMAIL}\r\nFrom: bob@example.com\r\nSubject: {SUBJECT}\r\n\r\nx\r\n"
    with pytest.raises(common.ScriptError, match="From"):
        submission.read_submission(eml(raw.encode()))


def test_read_submission_rejects_missing_subject(eml):
    email = message()
    del email["Subject"]
    with pytest.raises(common.ScriptError, match="Subject"):
        submission.read_submission(eml(email))


def test_read_submission_rejects_multiple_subjects(eml):
    raw = f"From: {EMAIL}\r\nSubject: {SUBJECT}\r\nSubject: Another\r\n\r\nx\r\n"
    with pytest.raises(common.ScriptError, match="Subject"):
        submission.read_submission(eml(raw.encode()))


@pytest.mark.parametrize("subject", ["", "   ", "Réentrancy", "Tab\there"])
def test_read_submission_rejects_subject(eml, subject):
    with pytest.raises(common.ScriptError, match="subject"):
        submission.read_submission(eml(message(subject=subject)))


def test_read_submission_rejects_encoded_non_ascii_subject(eml):
    raw = f"From: {EMAIL}\r\nSubject: =?UTF-8?B?UsOpZW50cmFuY3k=?=\r\n\r\nx\r\n"
    with pytest.raises(common.ScriptError, match="printable ASCII"):
        submission.read_submission(eml(raw.encode()))


def test_read_submission_rejects_attachment(eml):
    email = message()
    email.add_attachment("PoC", filename="poc.txt")
    with pytest.raises(common.ScriptError, match="attachments"):
        submission.read_submission(eml(email))


def test_read_submission_rejects_inline_image(eml):
    email = message()
    email.add_related(b"\x89PNG", maintype="image", subtype="png")
    with pytest.raises(common.ScriptError, match="image/png"):
        submission.read_submission(eml(email))


def test_main(eml, capsys):
    submission.main([str(eml(message()))])
    output = capsys.readouterr().out

    hash = common.compute_submission_hash(EMAIL, SUBJECT)
    assert printed(output, "Email") == EMAIL
    assert f"Subject:         {SUBJECT}\n" in output
    assert printed(output, "Submission hash") == HexBytes(hash).to_0x_hex()
    assert "Bond ID" not in output


def test_main_owner_matches_bond(eml, tmp_path, capsys):
    # The bond ID matches the one that `bond` prints for the same submission.
    argv = ["--owner", OWNER, "--email", EMAIL, "--subject", SUBJECT, "--no-salt"]
    bond.main(argv + ["--out", str(tmp_path / "bond.json")])
    bonded = capsys.readouterr().out

    submission.main([str(eml(message())), "--owner", OWNER])
    output = capsys.readouterr().out

    for label in ["Submission hash", "Bond ID", "BountyBond", "Owner"]:
        assert printed(output, label) == printed(bonded, label)


def test_main_error(eml):
    path = eml(message(subject="Réentrancy"))
    with pytest.raises(SystemExit, match="error: the subject is not printable"):
        common.run(lambda: submission.main([str(path)]))
