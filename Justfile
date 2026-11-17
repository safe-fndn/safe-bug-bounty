# Repo-wide command runner.
# Recipes run tools from the `.venv` virtual environment (created by
# `just deps`), so it does not need to be activated.

set shell := ["bash", "-euo", "pipefail", "-c"]

export PATH := justfile_directory() / ".venv/bin" + ":" + env("PATH")

# List available recipes.
default:
    @just --list

# Create the .venv virtual environment and install the pinned dependencies.
deps:
    test -d .venv || python3.13 -m venv .venv
    pip install -r requirements.txt

# Run the tests with pytest, passing through any arguments.
test *args:
    pytest {{args}}

# Run the Certora Prover on certora/conf/<conf>.conf, passing through any arguments.
# `--short_output` makes certoraRun wait on the job status (as it does in CI)
# instead of tailing the log, which does not return when the job finishes.
certora conf *args:
    certoraRun certora/conf/{{conf}}.conf --short_output {{args}}

# Write the Safe Transaction Builder bundle that deploys BountyBond.
deploy *args:
    python scripts/deploy.py {{args}}

# Write the Safe Transaction Builder bundle that posts a bond for a submission.
bond *args:
    python scripts/bond.py {{args}}

# Write the Safe Transaction Builder bundle that claims a bond back after its lockup.
claim *args:
    python scripts/claim.py {{args}}

# Regenerate requirements.txt from the latest direct dependencies.
requirements:
    rm -rf /tmp/safe-bug-bounty-venv && python3.13 -m venv /tmp/safe-bug-bounty-venv
    /tmp/safe-bug-bounty-venv/bin/pip install vyper titanoboa pytest certora-cli
    /tmp/safe-bug-bounty-venv/bin/pip freeze > requirements.txt
