# AGENTS.md

This file provides guidance to coding agents (such as Claude Code and Codex) when working with code in this repository.

## Overview

The on-chain submission bond for the Safe bug bounty (`contracts/BountyBond.vy`) and its scripts. Contracts are written in Vyper, tested with titanoboa and pytest, and formally verified with the Certora Prover, all from one Python (3.13) virtual environment.

[README.md](README.md) covers setup, what each script does and its options, and how to run tests and formal verification; read it first, and keep it as the single place for user-facing usage. This file only adds what matters when changing the code.

## Development

Commands are run with [`just`](https://github.com/casey/just); the `Justfile` documents each recipe. Recipes put `.venv/bin` first on `PATH`, so the virtual environment does not need to be activated. `just test` passes its arguments to `pytest`, so a single test runs with:

```sh
just test tests/contracts/test_bounty_bond.py::test_deploy
```

Run `just fix` and then `just lint` before committing: they format the Python, Markdown and `Justfile`, and lint the Python. Vyper and CVL sources are not formatted automatically, so follow the existing style in them by hand. `just` only shows the comment line directly above a recipe in `just --list`, and its formatter separates any earlier comment lines with a blank line, so keep recipe descriptions to one line.

### Tests

Shared fixtures (accounts, the mock token, the `BountyBond` contract) live in `tests/conftest.py`; `tests/contracts/conftest.py` only adds contract-test mocks. `pytest.ini` puts `scripts/` on `pythonpath`, so tests import script modules such as `common` directly. `tests/scripts/conftest.py` has fixtures that deploy `BountyBond` through the Safe singleton factory (`factory_bond`) and execute a bundle's transactions in titanoboa (`execute_bundle`).

### Scripts

Each script is a module with a `main(argv=None)` that tests call directly; the `Justfile` recipe of the same name runs it. Shared helpers are in `scripts/common.py`: the shared deployment options (`common.parser`) and argument types, compiling the contract, the factory address of the deployment (`common.bond_address`), the EIP-712 submission hash and bond ID, normalizing and salting submissions, and writing bundles. Invalid arguments are reported with `parser.error`; other errors meant for the user are raised as `common.ScriptError`, which `common.run` prints without a traceback.

Points to keep in mind:

- The scripts never use private keys or connect to a node, so they cannot read on-chain state (allowances, bond state); bundles are always written as if from a clean state, and the Safe UI's simulation surfaces failures.
- The deployment address depends on the exact init code, which includes a hash of the Vyper source in its metadata: any change to `contracts/BountyBond.vy`, even to comments, changes the address.
- `common.normalize_email` and `common.normalize_subject` define how submissions are hashed, and whoever checks bonds against submissions must apply exactly the same rules. Treat changes to them as breaking.
- The contract's `computeSubmissionHash(email, subject)` hashes its inputs as given (they must already be normalized), and must not be called on-chain or through an untrusted RPC node, since that reveals the email and subject.
- `scripts/submission.py` parses `.eml` files with the standard library `email` package and is deliberately strict; it registers `X-Original-Sender` as an address header on its own copy of the header registry, so `policy.default` is not changed.

### Formal verification

`just certora <conf>` runs `certoraRun certora/conf/<conf>.conf --short_output` (which polls the job status, as CI does, instead of tailing the log, which does not return), passing further arguments through. Add `--compilation_steps_only` to compile and type check without `CERTORAKEY`.

CI (`.github/workflows/certora.yml`) runs every `certora/conf/*.conf`. Confs inherit the shared options from `certora/base.conf` via `override_base_config`, so a conf only sets `verify` and `msg`. The prover verifies `certora/harness/BountyBondHarness.vy`, which imports `contracts/BountyBond.vy` as a module (`resolve_vyper_imports`) and adds views for the specs; shared harness declarations and invariants are in `certora/specs/common/Harness.spec`. Specs import `certora/specs/common/Token.spec`, which models `TOKEN` as the well-behaved ERC20 harness `certora/harness/Token.vy`.

### Dependencies

`requirements.txt` pins every direct and transitive dependency. The direct dependencies are listed in the `requirements` recipe of the `Justfile`. To add one (to that recipe first, keeping the list sorted alphabetically) or upgrade them all, run `just requirements`, which regenerates the file from a fresh virtual environment, and then `just setup` to update `.venv`.
