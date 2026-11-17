# Safe Bug Bounty

The on-chain submission bond for the Safe bug bounty. Each submission comes with a bond: the submitter locks 1337 SAFE in the `BountyBond` contract, which returns a unique bond ID, and can claim the tokens back after 30 days.

- `contracts/BountyBond.vy`: the bond contract (Vyper).
- `scripts/`: tools to deploy the contract, post a bond and claim it back.
- `tests/`: contract and script tests (pytest and titanoboa).
- `certora/`: formal verification specs (Certora Prover).

## Setup

Requires Python 3.13 and [`just`](https://github.com/casey/just).

```sh
just deps
```

This creates a `.venv` virtual environment and installs the pinned dependencies from `requirements.txt`. The `just` recipes use `.venv` directly, so it does not need to be activated. Run `just` to list all recipes.

## Tools

The scripts never use private keys or connect to a node. Each one writes a Safe Transaction Builder bundle (a JSON file in `bundles/`) that the owners of a Safe import into the Transaction Builder in the Safe UI, where it is simulated before being signed and executed.

`BountyBond` is deployed through the [Safe singleton factory](https://github.com/safe-fndn/safe-singleton-factory), so its address depends only on its deployment parameters. All scripts accept the same options, which default to the production values:

| Option | Default | |
| --- | --- | --- |
| `--chain-id` | `1` | Chain of the bundle |
| `--token` | `0x5aFE3855358E112B5647B952709E6165e1c1eEEe` | Bond token (SAFE) |
| `--amount` | `1337e18` | Bond amount, in the token's smallest unit |
| `--lockup` | `2592000` | Lockup in seconds (30 days) |
| `--create2-salt` | `0x00…00` | `CREATE2` salt |

### Deploy

```sh
just deploy [options]
```

Writes a bundle that deploys `BountyBond` and prints the address it will have.

### Post a bond

```sh
just bond --owner SAFE --email EMAIL --subject SUBJECT [options]
```

Writes a bundle that approves the bond amount and bonds the submission, with the Safe `--owner` as the bond owner. It prints the bond ID to include with the submission.

The email is trimmed and lowercased, and the subject is trimmed and must be printable ASCII. By default, a random suffix ` (0x<8 hex digits>)` is appended to the subject so that the bond cannot be linked to a guessed email and subject. **Submit with the subject exactly as printed**, since the suffix cannot be recovered. Use `--no-salt` to keep the subject as given.

### Claim a bond

```sh
just claim --owner SAFE --bond-id ID [options]
```

Writes a bundle that claims the bond back to the Safe that posted it. The claim only succeeds once the lockup has passed; otherwise the Safe UI simulation shows why it reverts.

## Development

### Tests

```sh
just test
```

Arguments are passed to `pytest`, for example:

```sh
just test tests/contracts/test_bounty_bond.py::test_deploy
```

### Formal verification

The [Certora Prover](https://docs.certora.com) proves three properties of `BountyBond`, each with a spec in `certora/specs/` and a config in `certora/conf/`:

- `ClaimAfterLockup`: a bond can always be claimed by its owner after its lockup.
- `NoOverClaim`: nobody can claim more tokens than they bonded.
- `BondLiveness`: nobody can prevent a new submission from being bonded.

Running the prover requires Java 19 or later (21 recommended) and a Certora key in `CERTORAKEY`:

```sh
just certora ClaimAfterLockup
```

To only compile and type check the specs, which does not need a key:

```sh
just certora ClaimAfterLockup --compilation_steps_only
```

CI runs the tests on every pull request, and every prover config on pull requests that change the contracts or specs.
