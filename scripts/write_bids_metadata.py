# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mne-bids>=0.14",
#   "pandas",
#   "openpyxl",
# ]
# ///
"""Write the dataset-level BIDS files: dataset_description.json,
participants.tsv + participants.json, README, and CHANGES.

Run this LAST, after every conversion is finished. write_raw_bids() rewrites
participants.tsv on every call, so running this first means your columns get
reset to bare defaults.

participants.json always describes exactly the columns participants.tsv
actually has -- no more. If the source dataset carries no demographics, the
honest output is a single participant_id entry saying so, not a set of
plausible-looking age/sex/handedness entries for columns that don't exist.

Usage:
    # see the real column names before mapping them -- don't guess
    uv run scripts/write_bids_metadata.py --list-columns /raw/demographics.xlsx

    # no demographics available
    uv run scripts/write_bids_metadata.py --bids-root /out/bids \\
        --name "My Study" --authors "Alice Author" --license CC0

    # with demographics
    uv run scripts/write_bids_metadata.py --bids-root /out/bids \\
        --name "My Study" --authors "Alice Author" --license CC0 \\
        --demographics-file /raw/demographics.xlsx \\
        --column-map '{"ParticipantID": "participant_id", "Age_years": "age", "Group": "group"}' \\
        --column-descriptions '{"group": {"Description": "Study group", "Levels": {"control": "Healthy control", "patient": "Clinical group"}}}'
"""
import argparse
import json
import os
import re
import sys

# BIDS defines these columns, so describing them is quoting the spec rather
# than inventing metadata. Anything else needs --column-descriptions.
STANDARD_COLUMNS = {
    "age": {"Description": "Age of the participant", "Units": "years"},
    "sex": {"Description": "Sex of the participant as reported by the source dataset",
            "Levels": {"F": "female", "M": "male", "O": "other"}},
    "handedness": {"Description": "Handedness of the participant as reported by the source dataset",
                   "Levels": {"L": "left", "R": "right", "A": "ambidextrous"}},
    "species": {"Description": "Binomial species name of the participant"},
}


def _read_table(path):
    import pandas as pd
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xls"):
        return pd.read_excel(path)
    return pd.read_csv(path, sep="\t" if ext == "tsv" else ",")


def build_participants(bids_root, demographics_file, column_map):
    import pandas as pd

    subjects = sorted(d[4:] for d in os.listdir(bids_root)
                      if d.startswith("sub-") and os.path.isdir(os.path.join(bids_root, d)))
    if not subjects:
        sys.exit(f"error: no sub-* directories under {bids_root} -- convert recordings first")

    if not (demographics_file and column_map):
        return pd.DataFrame({"participant_id": [f"sub-{s}" for s in subjects]})

    if "participant_id" not in column_map.values():
        sys.exit("error: --column-map must map one source column to 'participant_id'")
    df = _read_table(demographics_file)
    missing = set(column_map) - set(df.columns)
    if missing:
        sys.exit(f"error: --column-map names column(s) not in {demographics_file}: {sorted(missing)}")

    df = df[list(column_map)].rename(columns=column_map)
    df["participant_id"] = df["participant_id"].map(lambda v: "sub-" + re.sub(r"[^A-Za-z0-9]", "", str(v)))

    on_disk = {f"sub-{s}" for s in subjects}
    if on_disk - set(df["participant_id"]):
        print(f"warning: converted but absent from demographics: {sorted(on_disk - set(df['participant_id']))}", file=sys.stderr)
    if set(df["participant_id"]) - on_disk:
        print(f"warning: demographics rows with no converted data (dropped): {sorted(set(df['participant_id']) - on_disk)}", file=sys.stderr)
    df = df[df["participant_id"].isin(on_disk)]

    if "age" in df.columns:
        # BIDS privacy guidance: top-code age to limit re-identification.
        df["age"] = pd.to_numeric(df["age"], errors="coerce").clip(upper=89)

    df = df.fillna("n/a")
    return df[["participant_id"] + [c for c in df.columns if c != "participant_id"]]


def build_participants_json(columns, described):
    """Describe exactly the columns present -- never more."""
    out = {}
    for col in columns:
        if col in described:
            out[col] = described[col]
        elif col == "participant_id":
            out[col] = {"Description": "Unique participant identifier."}
            if len(columns) == 1:
                out[col]["Description"] += " No further participant information is provided by the source dataset."
        elif col in STANDARD_COLUMNS:
            out[col] = STANDARD_COLUMNS[col]
        else:
            out[col] = {"Description": f"As provided by the source dataset's {col!r} column."}
            print(f"warning: no --column-descriptions entry for {col!r}; wrote a minimal placeholder. "
                  f"Supply a real Description (and Levels, if categorical) if the source documents it.", file=sys.stderr)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list-columns", metavar="FILE", help="Print a demographics file's columns and exit")
    p.add_argument("--bids-root")
    p.add_argument("--name", help="Dataset Name")
    p.add_argument("--authors", help="Comma-separated author names")
    p.add_argument("--license", dest="data_license", help="e.g. CC0")
    p.add_argument("--doi", help="DatasetDOI, e.g. doi:10.18112/openneuro.ds000117.v1.0.0")
    p.add_argument("--references-and-links", help="Comma-separated URLs/DOIs: the paper, the source archive. This is where 'how the dataset should be cited' actually lands.")
    p.add_argument("--how-to-acknowledge", help="The source's own wording for how it wants to be credited")
    p.add_argument("--funding", help="Comma-separated grant/funding sources named by the source")
    p.add_argument("--ethics-approvals", help="Comma-separated ethics approval references named by the source")
    p.add_argument("--dataset-type", default="raw", choices=["raw", "derivative"])
    p.add_argument("--generated-by-name", help="Pipeline name. REQUIRED for --dataset-type derivative (GeneratedBy is mandatory there); should be a substring of the derivatives/<pipeline>/ folder name.")
    p.add_argument("--generated-by-description", help="What the pipeline did, from the source's own docs -- not a guess.")
    p.add_argument("--demographics-file")
    p.add_argument("--column-map", help='JSON {source_column: bids_column}, one mapping to "participant_id"')
    p.add_argument("--column-descriptions", help="JSON {bids_column: {Description, Levels, Units}} for columns BIDS doesn't already define")
    p.add_argument("--readme-text", help="README body (a minimal default is used if omitted)")
    args = p.parse_args()

    if args.list_columns:
        df = _read_table(args.list_columns)
        for col in df.columns:
            print(f"  {col!r}  (sample: {df[col].dropna().head(3).tolist()})")
        return

    if not args.bids_root or not args.name:
        sys.exit("error: --bids-root and --name are required")
    if args.dataset_type == "derivative" and not args.generated_by_name:
        sys.exit("error: --dataset-type derivative requires --generated-by-name")

    from mne_bids import make_dataset_description

    generated_by = None
    if args.generated_by_name:
        generated_by = [{"Name": args.generated_by_name}]
        if args.generated_by_description:
            generated_by[0]["Description"] = args.generated_by_description

    def _split(v):
        return [x.strip() for x in v.split(",") if x.strip()] if v else None

    make_dataset_description(
        path=args.bids_root,
        name=args.name,
        dataset_type=args.dataset_type,
        authors=[a.strip() for a in args.authors.split(",")] if args.authors else None,
        data_license=args.data_license,
        generated_by=generated_by,
        # Step 3 tells you to ask how the dataset should be cited; without these
        # there is nowhere to put the answer and it gets thrown away.
        doi=args.doi,
        references_and_links=_split(args.references_and_links),
        how_to_acknowledge=args.how_to_acknowledge,
        funding=_split(args.funding),
        ethics_approvals=_split(args.ethics_approvals),
        overwrite=True,
    )
    print("wrote dataset_description.json")

    if args.dataset_type == "derivative":
        # A derivatives sub-dataset inherits participants/README from its
        # parent. write_raw_bids() bootstraps placeholder copies into every
        # new root including this one; leaving them would state, wrongly,
        # that this sub-dataset has its own (empty) participant metadata.
        for fname in ("participants.tsv", "participants.json", "README", "CHANGES"):
            fpath = os.path.join(args.bids_root, fname)
            if os.path.exists(fpath):
                os.remove(fpath)
        print("removed placeholder participants/README (inherited from parent dataset)")
        return

    participants = build_participants(
        args.bids_root, args.demographics_file,
        json.loads(args.column_map) if args.column_map else None)
    participants.to_csv(os.path.join(args.bids_root, "participants.tsv"),
                        sep="\t", index=False, na_rep="n/a")
    print(f"wrote participants.tsv ({len(participants)} participants, columns: {list(participants.columns)})")

    described = json.loads(args.column_descriptions) if args.column_descriptions else {}
    with open(os.path.join(args.bids_root, "participants.json"), "w") as f:
        json.dump(build_participants_json(list(participants.columns), described), f, indent=2)
    print("wrote participants.json")

    with open(os.path.join(args.bids_root, "README"), "w", encoding="utf-8") as f:
        f.write(args.readme_text or f"{args.name}\n\nConverted to BIDS. See dataset_description.json for provenance.\n")
    print("wrote README")

    changes = os.path.join(args.bids_root, "CHANGES")
    if not os.path.exists(changes):
        with open(changes, "w", encoding="utf-8") as f:
            f.write("1.0.0 - Initial BIDS conversion\n")
        print("wrote CHANGES")


if __name__ == "__main__":
    main()
