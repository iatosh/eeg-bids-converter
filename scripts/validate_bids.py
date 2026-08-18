# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "bids-validator-deno",
# ]
# ///
"""Run the official BIDS validator against a converted dataset and print a
clean errors/warnings summary. None of the ~44 legacy notebooks in the old
archive ever ran a validator at all: this is the step that catches
whatever the rest of the pipeline got wrong (missing sidecar fields, n/a
where a value belongs, filename/entity mistakes) before you call the
conversion done.

Wraps the `bids-validator-deno` package (a self-contained Deno-based
validator, installable via uv/pip: no separate Node/Deno setup needed).

Exit code is 0 only if the validator reports zero errors (warnings alone
do not fail this script, but are printed and worth reviewing).

Usage:
    uv run scripts/validate_bids.py /out/bids
    uv run scripts/validate_bids.py /out/bids --ignore-warnings
"""
import argparse
import json
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bids_root")
    parser.add_argument("--ignore-warnings", action="store_true", help="Don't print warnings, only errors")
    parser.add_argument("--recursive", action="store_true", help="Also validate any derivatives/ subdirectories. Pass this whenever the dataset has a derivatives/<pipeline>/ tree: without it, the validator only checks the raw dataset and silently skips derivatives content.")
    args = parser.parse_args()

    cmd = ["bids-validator-deno", args.bids_root, "--format", "json"]
    if args.recursive:
        cmd.append("--recursive")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("error: could not parse validator output as JSON", file=sys.stderr)
        print("--- stdout ---", file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        print("--- stderr ---", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(2)

    issues = result.get("issues", {}).get("issues", []) if "issues" in result else result.get("issues", [])
    if isinstance(issues, dict):
        issues = issues.get("issues", [])

    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") == "warning"]

    print(f"BIDS validator: {len(errors)} error(s), {len(warnings)} warning(s)\n")

    for i in errors:
        code = i.get("code", i.get("key", "?"))
        loc = i.get("location", i.get("subCode", ""))
        reason = i.get("reason", i.get("issueMessage", ""))
        print(f"ERROR  [{code}] {loc}")
        if reason:
            print(f"       {reason}")

    if not args.ignore_warnings:
        for i in warnings:
            code = i.get("code", i.get("key", "?"))
            loc = i.get("location", i.get("subCode", ""))
            reason = i.get("reason", i.get("issueMessage", ""))
            print(f"WARN   [{code}] {loc}")
            if reason:
                print(f"       {reason}")

    if errors:
        print(f"\n{len(errors)} error(s) must be fixed before this dataset is valid BIDS.")
        sys.exit(1)
    print("\nNo errors. Dataset is valid BIDS.")


if __name__ == "__main__":
    main()
