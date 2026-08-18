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
import os
import subprocess
import sys



# The official validator checks every key it recognises, but it ignores keys it
# does not. Measured on a deliberately broken copy of references/examples:
#
#   RecordingDuration: "10.0" instead of 10.0   -> 1 error   (caught)
#   MISCChannelCount spelled MiscChannelCount   -> 0 errors  (ignored)
#   "age": [{...}] instead of "age": {...}      -> 0 errors  (ignored)
#   "Levels" spelled "levels"                   -> 0 errors  (ignored)
#
# A misspelled key is not a missing key to the validator, it is a key from some
# other vocabulary, so it passes. Three of those four defects ship in real lab
# templates. references/examples is a hand-checked dataset that the validator
# reports 0 errors on, so its key names and shapes are usable as the reference
# nothing else provides.

_REFS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references")
# examples/ is the validated dataset; templates/ additionally carries the
# OPTIONAL fields a real conversion may legitimately set. Reading both means a
# case error in an optional field is caught too.
KEY_SOURCES = [os.path.join(_REFS, "examples"), os.path.join(_REFS, "templates")]

# Data dictionaries: every column maps to one object, and these are the only
# keys allowed inside it (BIDS common-principles, PascalCase).
DICT_KEYS = {"LongName", "Description", "Format", "Levels", "Units",
             "Delimiter", "TermURL", "HED", "Minimum", "Maximum"}


def _known_keys(roots):
    """Every JSON key used anywhere in the reference files."""
    keys = set()

    def walk(obj):
        if isinstance(obj, dict):
            keys.update(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for root in roots:
      for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(dirpath, fn)) as f:
                        walk(json.load(f))
                except (OSError, json.JSONDecodeError):
                    pass
    return keys | DICT_KEYS


def check_against_example(bids_root):
    """Report what the validator structurally cannot: misspelled keys and
    malformed data dictionaries. Returns a list of message strings."""
    known = _known_keys(KEY_SOURCES)
    if not known:
        return []

    # examples/ and templates/ are edited by hand and must agree. If the same
    # key appears in both spellings, this checker would accept either and the
    # reader would copy whichever they happened to open. Say so rather than
    # silently picking one.
    problems = []
    by_fold = {}
    for k in known:
        by_fold.setdefault(k.lower(), set()).add(k)
    for variants in by_fold.values():
        if len(variants) > 1:
            problems.append(
                f"references/ disagrees with itself about {sorted(variants)}. "
                f"Fix the reference files; until then this check cannot judge "
                f"that key.")

    folded = {k.lower(): k for k in known}

    for dirpath, dirnames, filenames in os.walk(bids_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in sorted(filenames):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, bids_root)
            try:
                with open(path) as f:
                    doc = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                problems.append(f"{rel}: not readable as JSON ({exc})")
                continue
            if not isinstance(doc, dict):
                continue

            def inspect(node, where):
                if isinstance(node, list):
                    for item in node:
                        inspect(item, where)
                    return
                if not isinstance(node, dict):
                    return
                for key, value in node.items():
                    expected = folded.get(key.lower())
                    if expected and expected != key:
                        problems.append(
                            f"{rel}: key {key!r}{where} should be {expected!r}. "
                            f"The validator ignores keys it does not recognise, so "
                            f"this field is silently absent rather than wrong.")

                    # A data dictionary entry is one object per column. An array
                    # is the most common malformation and passes validation.
                    if isinstance(value, list) and value and isinstance(value[0], dict) \
                            and DICT_KEYS & set(value[0]):
                        problems.append(
                            f"{rel}: column {key!r} maps to a list. A data dictionary "
                            f"maps each column to one object: "
                            f"{{\"{key}\": {{...}}}}, not [{{...}}].")
                    else:
                        inspect(value, f" under {key!r}")

            inspect(doc, "")

    return problems


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

    extra = check_against_example(args.bids_root)
    for msg in extra:
        print(f"KEY    {msg}")

    if errors or extra:
        n = len(errors) + len(extra)
        print(f"\n{n} problem(s) must be fixed before this dataset is valid BIDS.")
        sys.exit(1)
    print("\nNo errors. Dataset is valid BIDS.")


if __name__ == "__main__":
    main()
