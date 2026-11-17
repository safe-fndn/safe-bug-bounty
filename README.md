# Safe Bug Bounty

The permissionless on-chain submission bond for the Safe bug bounty. To submit a report, you lock a fixed amount of SAFE in the `BountyBond` contract, and the bond is automatically tied to your submission. Once the lockup period ends, you can always claim the full bond back. The bond is intended to not cost honest researchers anything, as the bond is paid back in full; but increasing the barrier to entry for low-effort, LLM-generated reports.

## Setup

Requires Python 3.13 and [`just`](https://github.com/casey/just).

```sh
just setup
```

This creates a `.venv` virtual environment and installs the pinned dependencies from `requirements.txt`. The `just` recipes use `.venv` directly, so it does not need to be activated. Run `just` to list all recipes.

## Tools

The scripts never use private keys or connect to a node. Each one writes a Safe Transaction Builder bundle (a JSON file in `bundles/`) that the owners of a Safe import into the Transaction Builder in the Safe UI, where it is simulated before being signed and executed.

The scripts only write Safe Transaction Builder bundles. To use an EOA instead, send the transactions in the bundle yourself: each one has a target (`to`), a value and either raw call data or a contract method with its arguments, in order.

`BountyBond` is deployed through the [Safe singleton factory](https://github.com/safe-fndn/safe-singleton-factory), so its address depends only on its deployment parameters. All scripts accept the same options, which default to the production values:

| Option           | Default                                                              |                                           |
| ---------------- | -------------------------------------------------------------------- | ----------------------------------------- |
| `--chain-id`     | `1`                                                                  | Chain of the bundle                       |
| `--token`        | `0x5aFE3855358E112B5647B952709E6165e1c1eEEe`                         | Bond token (SAFE)                         |
| `--amount`       | `1337000000000000000000`                                             | Bond amount (1337.0)                      |
| `--lockup`       | `2592000`                                                            | Lockup in seconds (30 days)               |
| `--create2-salt` | `0x0000000000000000000000000000000000000000000000000000000000000000` | `CREATE2` salt                            |

### Deploy

```sh
just deploy [options]
```

Writes a bundle that deploys `BountyBond` and prints the address it will have.

### Post a bond

```sh
just bond --owner SAFE --email EMAIL --subject SUBJECT [options]
```

Writes a bundle that approves the bond amount and bonds the submission, with the Safe `--owner` as the bond owner. It prints the bond ID, which you need to claim the bond back.

The email is trimmed and lowercased, and the subject is trimmed and must be printable ASCII. By default, a random salt ` (0x<8 hex digits>)` is appended to the subject. It adds entropy to the submission so that it is harder to guess, and the bond cannot be linked to a guessed email and subject. **Submit with the subject exactly as printed**, since the salt cannot be recovered. Use `--no-salt` if you do not want this behaviour, for example if you want to derive your own entropy or need more than the salt provides.

### Claim a bond

```sh
just claim --owner SAFE --bond-id ID [options]
```

Writes a bundle that claims the bond back to the Safe that posted it. The claim only succeeds once the lockup has passed; otherwise the Safe UI simulation shows why it reverts.

## Development

### Repository layout

- `contracts/BountyBond.vy`: the bond contract (Vyper).
- `scripts/`: tools to deploy the contract, post a bond and claim it back.
- `tests/`: contract and script tests (pytest and titanoboa).
- `certora/`: formal verification specs (Certora Prover).

### Tests

The tests use [pytest](https://docs.pytest.org) and [titanoboa](https://github.com/vyperlang/titanoboa), which runs the contracts in a local Python EVM. Contract tests are in `tests/contracts/` and script tests in `tests/scripts/`.

```sh
just test
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
