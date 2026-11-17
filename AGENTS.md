# AGENTS.md

This file provides guidance to coding agents (such as Claude Code and Codex) when working with code in this repository.

## Overview

The on-chain submission bond for the Safe bug bounty (`contracts/BountyBond.vy`) and its scripts. A submitter locks a bond (1337 SAFE by default) with each submission, identified by a unique bond ID, and can claim it back after the lockup (30 days by default). Contracts are written in Vyper, tested with titanoboa and pytest, and formally verified with the Certora Prover, all from one Python (3.13) virtual environment. There are no lint or format tools yet.

## Development

Commands are run with [`just`](https://github.com/casey/just): the `Justfile` documents them, and `just` lists its recipes. Recipes put `.venv/bin` first on `PATH`, so the virtual environment does not need to be activated.

Setup (creates `.venv` with `python3.13` if it does not exist, and installs `requirements.txt` into it):

```sh
just setup
```

Run all tests (`pytest`, configured in `pytest.ini`):

```sh
just test
```

Run a single test (`just test` passes its arguments to `pytest`):

```sh
just test tests/contracts/test_bounty_bond.py::test_deploy
```

Shared test fixtures (accounts, the mock token, the `BountyBond` contract) live in `tests/conftest.py`; `tests/contracts/conftest.py` only adds contract-test mocks. `pytest.ini` puts `scripts/` on `pythonpath`, so tests import script modules such as `common` directly.

### Scripts

The scripts in `scripts/` never use private keys and never connect to a node. They compute everything offline, and all but `submission.py` write a Safe Transaction Builder bundle (a JSON file) that the owners of a Safe import into the Transaction Builder app in the Safe UI, which simulates the transactions before they are signed and executed. Shared helpers (argument types, compiling `contracts/BountyBond.vy`, the deployment address, the EIP-712 submission hash and bond ID, normalizing and salting submissions, and writing bundles) are in `scripts/common.py`. `tests/scripts/conftest.py` has fixtures that deploy `BountyBond` through the factory (`factory_bond`) and execute a bundle's transactions in titanoboa (`execute_bundle`).

`BountyBond` is deployed through the Safe singleton factory (`0x914d7Fec6aaC8cd542e72Bca78B30650d45643d7`, a `CREATE2` factory at the same address on every bytecode-compatible EVM chain), so its address follows from its deployment parameters. Every script therefore takes the same options, with the production values as defaults, and computes the contract's address from them (`common.bond_address`):

- `--chain-id` (default 1): the chain of the bundle.
- `--token` (default SAFE, `0x5aFE3855358E112B5647B952709E6165e1c1eEEe`), `--amount` (default `1337e18`, 1337 SAFE; scientific notation is parsed exactly and must give a whole number) and `--lockup` (default `2592000`, 30 days): the constructor arguments.
- `--create2-salt` (default `0x0...0`): the `CREATE2` salt, 32 hex bytes with `0x` prefix

Write the deployment bundle (`just deploy` runs `python scripts/deploy.py` from the repository root, passing its arguments through):

```sh
just deploy [--chain-id ID] [--token ADDRESS] [--amount WEI] [--lockup SECONDS] [--create2-salt SALT] [--out PATH]
```

The bundle is written to `--out` (default `bundles/deploy-<chain ID>.json`, ignored by git; relative paths are relative to the repository root), and the script prints the address the contract will have and its deployment parameters. If that address is already taken, the factory call reverts, which the Safe UI's simulation shows.

Write the bundle that posts a bond for a submission, owned by the Safe `--owner` (`just bond` runs `python scripts/bond.py`):

```sh
just bond --owner SAFE --email EMAIL --subject SUBJECT [--no-salt] [--out PATH] [shared options]
```

The email and subject are normalized with the rules that whoever checks bonds against submissions must apply as well (`common.normalize_email` and `common.normalize_subject`): the email is trimmed and lowercased; the subject is trimmed and otherwise kept exactly, and must be plain printable ASCII (anything else is rejected). Trimming removes ASCII whitespace only, and empty values are rejected. The contract's `computeSubmissionHash(email, subject)` is a view-only convenience that hashes the email and subject exactly as given, so they must be passed normalized; it must not be called on-chain or through an untrusted RPC node, since that reveals the email and subject. By default the script appends ` (0x<8 random hex digits>)` to the subject (`common.salt_subject`), so that the bond cannot be linked to a guessed email and subject; the submitter must then use the printed subject verbatim, since the salt cannot be recovered. `--no-salt` keeps the subject as given. The bundle has two transactions: `approve(<BountyBond>, amount)` on the token (always included, since the scripts cannot read the current allowance) and `bond(<submission hash>)`. It is written to `--out` (default `bundles/bond-<first 8 hex digits of the bond ID>.json`). The script prints the final subject, the submission hash, the bond ID, the `BountyBond` address and the lockup; the bond unlocks `--lockup` seconds after the `bond` transaction executes.

Write the bundle that claims a bond back to the Safe `--owner` that posted it (`just claim` runs `python scripts/claim.py`):

```sh
just claim --owner SAFE --bond-id ID [--out PATH] [shared options]
```

`--bond-id` is the bond ID that `just bond` printed (`0x` followed by 64 hex digits), and the shared options must match the deployment, since they determine the `BountyBond` address. The bundle has one transaction, `claim(<bond ID>)`, and is written to `--out` (default `bundles/claim-<first 8 hex digits of the bond ID>.json`). The script prints the bond ID, the `BountyBond` address and chain ID, the owner and the amount that will be returned. It cannot check the bond's state, so the claim only succeeds when the bundle is executed by the owner after the lockup has passed; otherwise the Safe UI's simulation shows the contract's revert reason (`locked`, `not owner`, `already claimed` or `unknown bond`).

Compute the submission hash of a submission email, and its bond ID for the Safe `--owner` if given (`just submission` runs `python scripts/submission.py`):

```sh
just submission FILE.eml [--owner SAFE] [shared options]
```

The `.eml` file is parsed with the standard library `email` package (`policy.default`, which unfolds and decodes headers). The email is the `addr_spec` of the single `From` address and the subject is the single `Subject` header, both normalized as in `just bond`. Errors are deliberately strict: anything other than exactly one `From` address and one `Subject`, a subject that is not printable ASCII, attachments, and any parts that are not `text/*` (or `multipart/*` containers) are rejected. The script writes no bundle; it prints the email, subject and submission hash, and with `--owner` the bond ID, the `BountyBond` address and chain ID, and the owner.

### Formal verification

Run the Certora Prover on one conf (needs `CERTORAKEY` in the environment and Java 19+, 21 recommended, for the local spec type check). `just certora <conf>` runs `certoraRun certora/conf/<conf>.conf --short_output`, passing any further arguments through (`--short_output` makes certoraRun poll the job status, as it does in CI; otherwise it tails the job log and does not return when the job finishes):

```sh
just certora ClaimAfterLockup
```

Each property has a spec in `certora/specs/` and a conf in `certora/conf/`. CI (`.github/workflows/certora.yml`) runs every `certora/conf/*.conf`. Confs inherit the shared options (files, compiler, `wait_for_results`) from `certora/base.conf` via `override_base_config`, so a conf only sets `verify` and `msg`. The prover verifies `certora/harness/BountyBondHarness.vy`, which imports `contracts/BountyBond.vy` as a module (`resolve_vyper_imports`) and adds views for the specs; shared harness declarations and invariants are in `certora/specs/common/Harness.spec`. Specs import `certora/specs/common/Token.spec`, which models `TOKEN` as the well-behaved ERC20 harness `certora/harness/Token.vy`. Add `--compilation_steps_only` (`just certora ClaimAfterLockup --compilation_steps_only`) to compile and type check without `CERTORAKEY`.

### Dependencies

`requirements.txt` pins every direct and transitive dependency to an exact version. The direct dependencies are `vyper`, `titanoboa`, `pytest` and `certora-cli`. To add one or upgrade them all, regenerate the file with `just requirements`, which installs the latest direct dependencies into a fresh virtual environment at `/tmp/safe-bug-bounty-venv` and writes its `pip freeze` to `requirements.txt` (add a new dependency to the recipe's `pip install` line first). Then run `just setup` to update `.venv`:

```sh
just requirements
just setup
```
