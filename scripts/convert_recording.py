# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mne>=1.6",
#   "mne-bids>=0.14",
#   "pandas",
#   "edfio",
#   "pybv>=0.7.3",
#   "eeglabio",
#   "curryreader",
# ]
# ///
"""Convert ONE raw recording into a correctly-written BIDS recording.

This is the fragile part of the pipeline: reader dispatch, channel
overrides, the line_freq-before-write idiom, a single events write path,
BIDSPath construction, all done the same way every time.

WHAT THIS SCRIPT DOES NOT DECIDE FOR YOU:
  - which files map to which subject/session/task/run (use inspect_dataset.py)
  - what the event codes mean (read the dataset's own documentation)
  - EEGReference/EEGGround/PowerLineFrequency/Manufacturer for this
    hardware (read the dataset's paper/README; never guess)
  - whether to filter or re-reference: for a raw BIDS conversion, don't.
    Processed data belongs in derivatives/, written with --desc.

SOURCE FORMATS: reading is delegated to mne.io.read_raw, so every format mne
supports works. That includes edf, bdf, vhdr, set, cnt, gdf, fif, cdt (Curry), mff (EGI),
lay (Persyst) and the rest. Do NOT assume a format is unsupported because it
looks unusual; check first. Only for a format mne genuinely cannot read
(custom .mat layouts, proprietary binary) build an mne.io.RawArray yourself,
raw.save() it as .fif, and pass that with --format fif. See
references/custom_formats.md. One write path for every source.

After writing, the output is read back and compared against the source
(sampling rate, duration, waveform). The BIDS validator checks structure, not
signal. Every silent corruption found in testing (a dropped .fdt, a
hardcoded sampling rate, a hand-parsed file read transposed) passed it with
zero errors.

EVENTS: pass at most ONE of --annotations-only (source has embedded
annotations mne reads) or --events-csv (an onset/duration/trial_type
table). Both at once produces two writers racing over one events.tsv.
Neither is correct only when the recording genuinely has no events.
With --events-csv, pass --events-descriptions too: mne-bids generates an
events.json automatically for the annotations path but not for this one.

Usage:
    uv run scripts/convert_recording.py \\
        --input /raw/P001_RestEC.edf --bids-root /out/bids \\
        --subject P001 --task RestEC \\
        --line-freq 50 \\
        --channel-types '{"HEOG":"eog","VEOG":"eog","ECG":"ecg"}' \\
        --annotations-only

    uv run scripts/convert_recording.py \\
        --input /raw/P001_Oddball.edf --bids-root /out/bids \\
        --subject P001 --task Oddball --line-freq 50 \\
        --events-csv /raw/P001_Oddball_events.csv
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import guess_format


def _diagnose_brainvision(input_path):
    """A .vhdr points at its .eeg/.vmrk siblings BY NAME. Reorganizing a
    messy archive renames the files but not the pointers, and mne then
    fails with a bare 'file not found' naming the stale target. Say what
    actually went wrong; don't edit the source dataset to fix it."""
    directory = os.path.dirname(os.path.abspath(input_path))
    stem = os.path.splitext(os.path.basename(input_path))[0]
    problems = []
    try:
        with open(input_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*(DataFile|MarkerFile)\s*=\s*(.+?)\s*$", line)
                if m and not os.path.exists(os.path.join(directory, m.group(2))):
                    expected = stem + (".eeg" if m.group(1) == "DataFile" else ".vmrk")
                    sibling = "exists" if os.path.exists(os.path.join(directory, expected)) else "also missing"
                    problems.append(f"  {m.group(1)}={m.group(2)!r} not found; {expected!r} {sibling}")
    except OSError:
        return ""
    if not problems:
        return ""
    return ("\nThis .vhdr's internal file pointers are stale:\n" + "\n".join(problems) +
            "\nCopy the triplet to a scratch directory and correct the DataFile:/MarkerFile: "
            "lines there. Do not edit files in the source dataset.")


def build_raw(input_path: str, format_override: str | None, preload: bool = False):
    """Read the source with mne's own dispatcher.

    Deliberately NOT a hand-maintained extension->reader table. mne ships 30
    read_raw_* functions and grows more; any local subset silently sends
    readable formats down the "write your own binary parser" path, which is
    how a Curry .cdt got parsed by hand into a transposed data matrix that
    passed the BIDS validator with zero errors.
    """
    import mne

    ext = (format_override or input_path.rsplit(".", 1)[-1]).lower()
    reader_name, _ = guess_format(ext)
    reader = getattr(mne.io, reader_name) if reader_name else mne.io.read_raw
    try:
        return reader(input_path, preload=preload, verbose=False)
    except FileNotFoundError as exc:
        raise SystemExit(f"error reading {input_path}: {exc}" +
                         (_diagnose_brainvision(input_path) if ext == "vhdr" else ""))
    except ValueError as exc:
        raise SystemExit(
            f"error: mne could not read {input_path}: {exc}\n"
            f"If this format genuinely has no mne reader, build a Raw yourself, raw.save() it "
            f"as .fif, and pass that with --format fif. But check `mne.io.read_raw` first.")


def apply_events_csv(raw, events_csv_path: str):
    import pandas as pd

    df = pd.read_csv(events_csv_path)
    if "onset" not in df.columns:
        # Be forgiving of the common "onset_sec" naming seen in lab exports.
        rename = {}
        for col in df.columns:
            if col.lower() in ("onset_sec", "onset_s", "onset_time"):
                rename[col] = "onset"
            elif col.lower() in ("duration_sec", "duration_s"):
                rename[col] = "duration"
        df = df.rename(columns=rename)
    if "onset" not in df.columns:
        raise SystemExit("error: --events-csv must have an 'onset' column (seconds)")
    if "duration" not in df.columns:
        # BIDS requires the column to exist; 0 is the correct value for
        # instantaneous/point events (the common case for trigger-coded
        # tasks that don't record an explicit event duration).
        df["duration"] = 0.0
    return df


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="Path to the raw recording file")
    parser.add_argument("--format", dest="format_override", default=None, help="Override format detection (edf/bdf/vhdr/set/cnt/gdf/fif); default: infer from --input extension")
    parser.add_argument("--bids-root")
    parser.add_argument("--subject", help="Sanitized subject label, no 'sub-' prefix")
    parser.add_argument("--session", default=None, help="Sanitized session label, no 'ses-' prefix")
    parser.add_argument("--task", help="Sanitized task label")
    parser.add_argument("--run", default=None, help="Run index, e.g. 1 or 01")
    parser.add_argument("--acq", default=None)
    parser.add_argument("--desc", default=None, help="BIDS 'desc' entity (e.g. 'preproc'). Only for writing into a derivatives/<pipeline>/ tree to distinguish a processed version from the raw recording it was derived from: never set this when writing to the raw dataset itself. See SKILL.md's derivatives step.")
    parser.add_argument("--line-freq", default=None, help="Power line frequency in Hz (50 or 60), or 'unknown'. One of several fields mne-bids cannot infer; anything left unset is reported after the write.")
    parser.add_argument("--channel-types", default=None, help='JSON dict of {channel_name: bids_type}, e.g. \'{"HEOG":"eog"}\'. Lowercase MNE type names (eog/ecg/emg/misc/stim).')
    parser.add_argument("--rename-channels", default=None, help='JSON dict of {old_name: new_name} to clean up messy source channel labels before writing.')
    parser.add_argument("--drop-channels", default=None, help="Comma-separated channel names to drop before writing (e.g. unused/empty channels).")
    parser.add_argument("--montage", default=None, help="Standard montage name (e.g. standard_1020, GSN-HydroCel-128) to attach, producing electrodes.tsv + coordsystem.json. Use ONLY when the recording really used that layout and channel names match it. A generic cap layout is not a substitute for digitized positions: if you only know the scheme, leave this off and set EEGPlacementScheme via patch_sidecar.py instead. --list-montages prints the available names.")
    parser.add_argument("--list-montages", action="store_true", help="Print the standard montage names mne ships and exit")
    parser.add_argument("--annotations-only", action="store_true", help="Write events.tsv from raw.annotations (mutually exclusive with --events-csv)")
    parser.add_argument("--events-csv", default=None, help="Path to a CSV with onset,duration,trial_type[,value] columns (seconds); written directly, bypassing mne-bids' annotation-derived events (mutually exclusive with --annotations-only)")
    parser.add_argument("--events-descriptions", default=None, help='Only with --events-csv: JSON dict documenting non-obvious event columns for the accompanying events.json, e.g. \'{"trial_type": {"Description": "Event category", "Levels": {"standard": "Frequent tone", "target": "Rare tone"}}}\'. Any --events-csv column not covered gets a generic placeholder description so the validator does not flag it as undocumented: pass real Levels here whenever you know what the codes mean (see references/custom_formats.md).')
    parser.add_argument("--output-format", default="auto", help="BIDS output format: auto (default; keeps source format when BIDS-native and no preload is needed, else falls back to BrainVision), or explicitly EDF/BrainVision/EEGLAB (BDF is not a valid explicit target for mne-bids: only reachable via 'auto' with no channel edits).")
    parser.add_argument("--anonymize-daysback", type=int, default=None, help="If set, shifts recording dates back this many days (mne-bids anonymize=). Use for any dataset with real subject-identifying dates.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-preload", action="store_true", help="Only needed if the source data must be preloaded (e.g. to modify channels) AND --output-format is not 'auto'.")
    args = parser.parse_args()

    if args.list_montages:
        import mne
        print("\n".join(mne.channels.get_builtin_montages()))
        return

    if args.annotations_only and args.events_csv:
        print("error: pass at most one of --annotations-only / --events-csv, never both", file=sys.stderr)
        sys.exit(1)
    if not args.input or not args.bids_root or not args.subject or not args.task:
        print("error: --input, --bids-root, --subject and --task are required", file=sys.stderr)
        sys.exit(1)

    line_freq = None
    if args.line_freq is not None and args.line_freq.strip().lower() != "unknown":
        try:
            line_freq = float(args.line_freq)
        except ValueError:
            print(f"error: --line-freq must be a number or 'unknown', got {args.line_freq!r}", file=sys.stderr)
            sys.exit(1)

    import mne
    from mne_bids import BIDSPath, write_raw_bids

    ext = (args.format_override or args.input.rsplit(".", 1)[-1]).lower()
    _, src_bids_format = guess_format(ext)

    # format="auto" only works when mne-bids can copy the source through
    # untouched, which needs the source to already be a BIDS format AND the
    # data not to be preloaded. Anything else has to name a target format
    # explicitly, and naming one requires preload. Deciding this from the
    # source format rather than from whether channels are being edited is the
    # difference between a GDF file converting and a GDF file dying on
    # "The input data is in a file format not supported by BIDS".
    #
    # mne-bids' explicit `format=` accepts only BrainVision/EDF/EEGLAB/FIF, so
    # BDF is a valid BIDS format but not a valid explicit target, so it stays on
    # the copy-through path unless something else forces a preload.
    #
    # EEGLAB is deliberately NOT on this list even though BIDS accepts it. An
    # EEGLAB recording is a .set header plus a .fdt holding the samples, and
    # mne-bids' copy-through path writes only the .set, so the output reads back
    # as "File ..._eeg.fdt not found" while the validator reports zero errors.
    # Preloading and writing EEGLAB explicitly produces a single self-contained
    # .set instead. Costs one full read into memory; correctness is worth it.
    bids_native = src_bids_format in ("EDF", "BrainVision", "BDF")
    needs_preload = bool(args.rename_channels or args.drop_channels or args.channel_types)
    if args.output_format == "auto" and not bids_native:
        needs_preload = True

    raw = build_raw(args.input, args.format_override, preload=needs_preload)

    output_format = args.output_format
    if needs_preload and output_format == "auto":
        output_format = src_bids_format if src_bids_format in ("EDF", "BrainVision", "EEGLAB") else "BrainVision"

    if line_freq is not None:
        raw.info["line_freq"] = line_freq

    if args.rename_channels:
        raw.rename_channels(json.loads(args.rename_channels))

    if args.drop_channels:
        drop = [c.strip() for c in args.drop_channels.split(",") if c.strip()]
        raw.drop_channels(drop)

    if args.channel_types:
        raw.set_channel_types(json.loads(args.channel_types))

    if args.montage:
        # Applied here, before the write, so electrodes.tsv/coordsystem.json
        # fall out of the same write_raw_bids call. Doing it as a later
        # read-modify-write pass over an already-written recording is how
        # you end up deleting the data file out from under a lazy Raw.
        montage = mne.channels.make_standard_montage(args.montage)
        matched = [ch for ch in raw.ch_names if ch in set(montage.ch_names)]
        if not matched:
            raise SystemExit(
                f"error: no channel in {raw.ch_names[:8]}... matches montage {args.montage!r}. "
                f"Rename channels to the montage's own names first (--rename-channels), or drop --montage.")
        raw.set_montage(montage, on_missing="warn")
        print(f"montage {args.montage}: {len(matched)}/{len(raw.ch_names)} channels positioned")

    events_df = None
    if args.events_csv:
        events_df = apply_events_csv(raw, args.events_csv)

    bids_path = BIDSPath(
        subject=args.subject,
        session=args.session,
        task=args.task,
        run=args.run,
        acquisition=args.acq,
        description=args.desc,
        root=args.bids_root,
        datatype="eeg",
        suffix="eeg",
    )

    anonymize = {"daysback": args.anonymize_daysback} if args.anonymize_daysback is not None else None

    write_kwargs = dict(
        overwrite=args.overwrite,
        format=output_format,
        allow_preload=args.allow_preload or needs_preload,
        anonymize=anonymize,
        verbose=False,
    )

    def write(raw_obj, path):
        """write_raw_bids, minus the electrode positions BIDS won't accept.

        Plenty of EEGLAB .set files carry chanlocs in a head coordinate frame
        with no nasion/LPA/RPA, and mne-bids refuses the whole write rather
        than the positions. Fabricating the missing landmarks would produce
        exactly the invented electrodes.tsv this skill tells you never to
        write, so the positions go and the recording stays.
        """
        try:
            return write_raw_bids(raw_obj, path, **write_kwargs)
        except RuntimeError as exc:
            if "nasion" not in str(exc):
                raise
            print(f"  dropping electrode positions: {exc}")
            print("  (they lack the fiducials BIDS requires; set EEGPlacementScheme instead)")
            raw_obj.set_montage(None)
            return write_raw_bids(raw_obj, path, **write_kwargs)

    if events_df is not None:
        # Write the recording first, then the events.tsv/json ourselves --
        # this is the one clean way to fully bypass mne-bids' own
        # annotation-derived events.tsv so there is exactly one writer of
        # events.tsv, never two (see module docstring).
        raw.set_annotations(None)
        write(raw, bids_path)
        events_path = bids_path.copy().update(suffix="events", extension=".tsv")
        cols = ["onset", "duration"] + [c for c in events_df.columns if c not in ("onset", "duration")]
        events_df[cols].to_csv(events_path.fpath, sep="\t", index=False, na_rep="n/a")

        # Always write the accompanying events.json too: an --events-csv
        # write path has no mne-bids equivalent of the auto-generated one
        # the --annotations-only path gets for free, and an undocumented
        # extra column (e.g. a raw numeric "code") is exactly the kind of
        # thing the validator flags as a warning and a human reviewer
        # should not have to notice is missing.
        descriptions = json.loads(args.events_descriptions) if args.events_descriptions else {}
        extra_cols = [c for c in cols if c not in ("onset", "duration")]
        events_json = {}
        for col in extra_cols:
            events_json[col] = descriptions.get(col, {"Description": f"See dataset documentation for the meaning of '{col}'."})
        if events_json:
            events_json_path = bids_path.copy().update(suffix="events", extension=".json")
            with open(events_json_path.fpath, "w") as f:
                json.dump(events_json, f, indent=2)
    else:
        write(raw, bids_path)

    print(f"Wrote {bids_path.fpath}")
    verify_written(raw, bids_path)
    report_undetermined(bids_path, converted=(output_format not in ("auto", src_bids_format)))


def verify_written(source_raw, bids_path):
    """Read the file back and check it still holds the source signal.

    write_raw_bids() reports success in cases where the output is wrong or
    empty: an EEGLAB .set written without its .fdt companion (all the data
    missing), a converter that changed the sampling rate, a source built by a
    hand-written parser that scrambled the samples. The BIDS validator catches
    none of these: it checks structure, not signal. This is the only step that
    compares what came out against what went in.
    """
    import mne
    import numpy as np

    try:
        out = mne.io.read_raw(str(bids_path.fpath), preload=False, verbose=False)
    except Exception as exc:
        raise SystemExit(
            f"error: wrote {bids_path.fpath} but cannot read it back: {exc}\n"
            f"The output is unusable. For an EEGLAB .set this usually means the .fdt "
            f"companion was not written: re-run with --output-format BrainVision.")

    problems = []
    if out.info["sfreq"] != source_raw.info["sfreq"]:
        problems.append(f"sampling rate {source_raw.info['sfreq']} -> {out.info['sfreq']} Hz")

    # EDF pads the final data record out to a whole second; anything else is wrong.
    grew = (out.n_times - source_raw.n_times) / source_raw.info["sfreq"]
    if not -1e-9 <= grew <= 1.0:
        problems.append(f"duration {source_raw.n_times / source_raw.info['sfreq']:.3f}s -> "
                        f"{out.n_times / out.info['sfreq']:.3f}s")

    k, n = min(8, len(out.ch_names)), min(source_raw.n_times, out.n_times, 50000)
    if k and n > 1:
        a = source_raw.get_data(picks=range(k), start=0, stop=n)
        b = out.get_data(picks=range(k), start=0, stop=n)
        r = np.nan_to_num([np.corrcoef(a[i], b[i])[0, 1] for i in range(k)])
        if r.min() < 0.99:
            problems.append(f"waveform correlation with source is {r.min():.4f} "
                            f"(scrambled samples, wrong channel order, or wrong parse)")

    if problems:
        raise SystemExit("error: the written file does not match the source:\n  " +
                         "\n  ".join(problems))
    print("  verified: sampling rate, duration and waveform match the source")


# Fields mne-bids writes as "n/a" because nothing in the raw file can tell
# it the answer. They are not errors: but each one has to be a decision
# somebody made, not a default nobody noticed.
NO_INFER_FIELDS = ("PowerLineFrequency", "EEGReference", "EEGGround",
                   "Manufacturer", "ManufacturersModelName", "EEGPlacementScheme")


def report_undetermined(bids_path, converted=False):
    sidecar = bids_path.copy().update(suffix="eeg", extension=".json").fpath
    try:
        with open(sidecar) as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    unset = [k for k in NO_INFER_FIELDS if str(meta.get(k, "n/a")).lower() in ("n/a", "none", "")]

    # mne-bids fills Manufacturer from a FILE FORMAT lookup (config.MANUFACTURERS:
    # .vhdr -> "Brain Products", .cdt -> "Curry", .fif -> "Elekta"), which names the
    # format's vendor, not the amplifier that recorded the data. It is not "n/a", so
    # the check above lets it through: a Neuroscan recording written as BrainVision
    # comes out claiming Brain Products hardware, and no validator objects.
    #
    # Only worth saying when the format actually changed: a BrainVision source
    # written as BrainVision really is Brain Products, and warning about it would
    # train the reader to skip this line.
    from mne_bids.config import MANUFACTURERS
    if converted and str(meta.get("Manufacturer", "")) in set(MANUFACTURERS.values()) - {"n/a"}:
        print(f"  Manufacturer is {meta['Manufacturer']!r}: that is the vendor of the format this "
              f"was CONVERTED to, not the recording hardware. Set the real one via patch_sidecar.py.")

    if not unset:
        return
    print("  still undetermined: " + ", ".join(unset))
    print("  -> check the dataset's documentation, then ask the user; set what you learn with")
    print("     patch_sidecar.py. Leave n/a only for what neither source can answer.")


if __name__ == "__main__":
    main()
