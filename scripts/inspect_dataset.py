# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Survey a raw dataset: what files are there, which are readable EEG
recordings, and -- with --pattern -- what BIDS entities your filename regex
would extract from each one.

Run without --pattern first to see what you're dealing with, then re-run
with a candidate --pattern until every recording maps to sensible entities.
Doing this before converting anything is the whole point: a regex that
"matches" but pulls the session number into the task label is the single
easiest way to produce a wrong-but-valid BIDS tree.

Usage:
    uv run scripts/inspect_dataset.py <raw_root>
    uv run scripts/inspect_dataset.py <raw_root> --pattern '(?P<subject>P\\d+)_(?P<task>[A-Za-z]+)'
    uv run scripts/inspect_dataset.py <raw_root> --pattern '...' --out entities.json

--pattern takes named groups: subject (required), session, task, run, acq
(all optional -- omit any the dataset doesn't have; don't invent a ses-01
just for symmetry). Captured values are sanitized to alphanumeric-only per
BIDS label rules, so check the printed result still reads correctly --
"s01_v2" silently becomes "s01v2".

The pattern matches the path relative to raw_root, so entities held in
directory names are reachable too:
    'Datasets/(?P<task>[A-Za-z]+)/raw/'      task from the folder
    'sub_(?P<subject>\\d+)/(?P<session>ses\\d)/'
A dataset with only one participant may not name it anywhere; supply the
subject label yourself at conversion time rather than inventing a group
for it.

--out writes {relpath: entities} as JSON, for driving a conversion loop.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import COMPANION_EXTENSIONS, EVENT_SIDECAR_EXTENSIONS, guess_format, sanitize_label

ENTITY_ORDER = ["subject", "session", "task", "acq", "run"]


def scan(raw_root):
    """Return (recordings, other_files, extension_counts)."""
    recordings, other, counts = [], [], {}
    for dirpath, dirnames, filenames in os.walk(raw_root):
        # Prune hidden directories in place: a dataset cloned from git
        # otherwise reports its .git internals as unreadable "recordings".
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
            counts[ext] = counts.get(ext, 0) + 1
            # A BrainVision .eeg/.vmrk or EEGLAB .fdt is part of another
            # recording, not one of its own -- only the file mne actually
            # opens (.vhdr, .set) counts as a recording.
            # A BrainVision .eeg belongs to the .vhdr sitting next to it --
            # but Nihon Kohden's own raw recordings are ALSO named .EEG (with
            # .PNT/.LOG companions). Skipping every .eeg unconditionally
            # reports a whole Nihon Kohden dataset as "0 readable recordings",
            # silently, which is the worst way to lose data. Only treat it as
            # a companion when the .vhdr it would belong to actually exists.
            if ext == "eeg" and not os.path.exists(
                    os.path.join(dirpath, fn.rsplit(".", 1)[0] + ".vhdr")):
                pass
            elif ext in COMPANION_EXTENSIONS:
                continue
            relpath = os.path.relpath(os.path.join(dirpath, fn), raw_root)
            reader, bids_format = guess_format(ext)
            if reader:
                recordings.append({"relpath": relpath, "path": os.path.join(dirpath, fn),
                                   "extension": ext, "reader": reader, "bids_format": bids_format})
            else:
                other.append({"relpath": relpath, "extension": ext,
                              "maybe_events": ext in EVENT_SIDECAR_EXTENSIONS})
    recordings.sort(key=lambda r: r["relpath"])
    other.sort(key=lambda r: r["relpath"])
    return recordings, other, counts


def extract(relpath, pattern):
    # Matched against the path relative to raw_root, not just the basename:
    # datasets routinely encode subject/session/task in directory names
    # (sub_01/rest/recording.bdf) rather than in the filename.
    m = re.search(pattern, relpath)
    if not m:
        return None
    groups = m.groupdict()
    return {k: sanitize_label(groups[k]) for k in ENTITY_ORDER
            if k in groups and groups[k] is not None}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("raw_root")
    p.add_argument("--pattern", help="Regex with named groups (subject required) to dry-run against every recording")
    p.add_argument("--out", help="Write {relpath: entities} JSON here (requires --pattern)")
    args = p.parse_args()

    if not os.path.isdir(args.raw_root):
        sys.exit(f"error: not a directory: {args.raw_root}")
    if args.out and not args.pattern:
        sys.exit("error: --out requires --pattern")

    recordings, other, counts = scan(args.raw_root)
    print(f"{sum(counts.values())} files: {dict(sorted(counts.items(), key=lambda kv: -kv[1]))}")
    print(f"{len(recordings)} readable EEG recordings\n")

    if not args.pattern:
        for r in recordings:
            print(f"  {r['relpath']}  ({r['reader']})")
        unreadable = sorted({f["extension"] for f in other} - EVENT_SIDECAR_EXTENSIONS)
        maybe_events = [f["relpath"] for f in other if f["maybe_events"]]
        if maybe_events:
            print(f"\npossible external event/metadata files ({len(maybe_events)}):")
            for m in maybe_events[:20]:
                print(f"  {m}")
            if len(maybe_events) > 20:
                print(f"  ... and {len(maybe_events) - 20} more")
        if unreadable:
            print(f"\nno native mne reader for: {unreadable}")
            print("  -> these need a custom loader; see references/custom_formats.md")
        if not recordings:
            print("\nNothing readable found. Check the path, or the data needs a custom loader.")
        return

    if "subject" not in args.pattern:
        # Legitimate for a single-participant dataset, which often names the
        # participant nowhere. Anything else means a forgotten group.
        print("note: pattern captures no subject; pass --subject explicitly per recording.\n"
              "      Correct for a single-participant dataset -- otherwise add (?P<subject>...).\n")

    results, failed = {}, []
    for r in recordings:
        entities = extract(r["relpath"], args.pattern)
        if entities is None:
            failed.append(r["relpath"])
            print(f"NO MATCH  {r['relpath']}")
        else:
            results[r["relpath"]] = entities
            print(f"OK        {r['relpath']}  ->  " + " ".join(f"{k}={v}" for k, v in entities.items()))

    print(f"\n{len(results)} matched, {len(failed)} unmatched, of {len(recordings)} recordings")
    if failed:
        print("Fix the pattern, or handle the unmatched files as documented exceptions, before converting.")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
