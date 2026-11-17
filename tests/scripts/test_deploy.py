import json

import boa
import pytest

import common
import deploy


@pytest.fixture
def execute(execute_bundle):
    """Executes the bundle at `path` and returns the contract it deployed."""

    def execute(path):
        [tx] = json.loads(path.read_text())["transactions"]
        assert (tx["to"], tx["value"]) == (common.FACTORY, "0")
        [computation] = execute_bundle(path)
        return boa.load_partial(common.CONTRACT).at(computation.output)

    return execute


def predicted(output):
    return output.split("BountyBond will be deployed at ")[1].split()[0]


def test_main(factory, execute, tmp_path, capsys):
    path = tmp_path / "deploy.json"
    deploy.main(["--out", str(path)])

    output = capsys.readouterr().out
    bond = execute(path)
    assert bond.address == predicted(output)
    assert bond.TOKEN() == common.SAFE_TOKEN
    assert bond.AMOUNT() == 1337 * 10**18
    assert bond.LOCKUP() == 2_592_000
    assert f"token:        {common.SAFE_TOKEN}" in output
    assert f"amount:       {1337 * 10**18}" in output
    assert "lockup:       2592000" in output
    assert f"CREATE2 salt: 0x{'00' * 32}" in output
    assert f"Transaction bundle: {path}" in output
    assert json.loads(path.read_text())["chainId"] == "1"


def test_main_args(factory, execute, token, tmp_path, capsys):
    path = tmp_path / "deploy.json"
    argv = ["--token", str(token.address).lower(), "--amount", "1e18"]
    argv += ["--lockup", "60", "--create2-salt", "0x" + "42" * 32]
    deploy.main(argv + ["--out", str(path)])
    output = capsys.readouterr().out

    bond = execute(path)
    assert bond.address == predicted(output)
    assert f"CREATE2 salt: 0x{'42' * 32}" in output
    assert bond.TOKEN() == token.address
    assert bond.AMOUNT() == 10**18
    assert bond.LOCKUP() == 60


def test_main_default_out(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    deploy.main(["--chain-id", "100"])
    bundle = json.loads((tmp_path / "bundles" / "deploy-100.json").read_text())
    assert bundle["chainId"] == "100"


def test_main_invalid_amount(capsys):
    with pytest.raises(SystemExit) as exit:
        deploy.main(["--amount", "1.5"])
    assert exit.value.code == 2
    assert "argument --amount: not a uint256: 1.5" in capsys.readouterr().err


def test_main_invalid_create2_salt(capsys):
    # Integer salts are not accepted, only 0x followed by 64 hex digits.
    with pytest.raises(SystemExit) as exit:
        deploy.main(["--create2-salt", "1"])
    assert exit.value.code == 2
    assert "argument --create2-salt: not 32 bytes of hex: 1" in capsys.readouterr().err
