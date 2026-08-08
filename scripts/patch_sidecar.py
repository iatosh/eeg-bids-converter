# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mne-bids>=0.14",
# ]
# ///
"""Patch fields into one or more *_eeg.json sidecars that mne-bids cannot
infer from the raw data itself -- chiefly EEGReference, EEGGround,
Manufacturer, ManufacturersModelName, CapManufacturer, EEGPlacementScheme.
(PowerLineFrequency should instead be set via convert_recording.py's
--line-freq, which sets raw.info["line_freq"] before the initial write --
that's the correct mne-bids idiom; patching it here after the fact works
too but isn't preferred.)

These values are always dataset-level facts you get from the original
paper/README/hardware documentation -- never invent or guess them. If a
field is genuinely unknown after checking, leave it "n/a" rather than
patch in a plausible-sounding guess.

Matches sidecars by BIDSPath entity filters: give --subject/--session/
--task/--run to narrow to specific recordings, or omit all of them to
patch every *_eeg.json in the dataset with the same values (typical when
one hardware setup and one reference scheme applies to the whole dataset).

Usage:
    uv run scripts/patch_sidecar.py --bids-root /out/bids \\
        --entries '{"EEGReference": "average", "EEGGround": "AFz",
                     "Manufacturer": "BrainProducts"}'

    # narrow to one subject/task
    uv run scripts/patch_sidecar.py --bids-root /out/bids \\
        --subject P001 --task RestEC \\
        --entries '{"EEGReference": "average"}'
"""
import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bids-root", required=True)
    parser.add_argument("--subject", default=None)
    parser.add_argument("--session", default=None)
    parser.add_argument("--task", default=None)
    parser.add_argument("--run", default=None)
    parser.add_argument("--entries", required=True, help="JSON dict of sidecar key/value pairs to merge in (overwrites existing keys of the same name)")
    args = parser.parse_args()

    entries = json.loads(args.entries)
    if not entries:
        print("error: --entries is empty, nothing to patch", file=sys.stderr)
        sys.exit(1)

    from mne_bids import BIDSPath, update_sidecar_json

    search_path = BIDSPath(
        subject=args.subject,
        session=args.session,
        task=args.task,
        run=args.run,
        root=args.bids_root,
        datatype="eeg",
        suffix="eeg",
        extension=".json",
        check=False,
    )
    matches = search_path.match(ignore_json=False)

    # match() walks the whole tree including derivatives/, but resolves
    # everything it finds against --bids-root -- so a derivatives recording
    # comes back as a raw-root path that doesn't exist. Keeping only paths
    # that are really there confines each run to its own dataset; patch a
    # derivatives dataset by pointing --bids-root at it directly.
    kept = [bp for bp in matches if os.path.exists(bp.fpath)]
    if len(kept) != len(matches):
        print(f"skipping {len(matches) - len(kept)} match(es) belonging to another dataset "
              f"(likely under derivatives/ -- patch those with --bids-root set to that directory)")
    matches = kept

    if not matches:
        print(f"error: no *_eeg.json sidecars matched under {args.bids_root} with the given filters", file=sys.stderr)
        sys.exit(1)

    for bp in matches:
        update_sidecar_json(bp, entries, verbose=False)
        print(f"patched {bp.fpath}")

    print(f"\n{len(matches)} sidecar(s) patched with: {json.dumps(entries)}")


if __name__ == "__main__":
    main()
