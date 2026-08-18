---
name: eeg-bids-converter
description: Converts arbitrary raw/messy EEG datasets (EDF, BrainVision, EEGLAB .set, Biosemi BDF, GDF, CNT, Curry .cdt, custom MATLAB .mat structs, or anything else mne can read or be coerced into) into a spec-valid BIDS (Brain Imaging Data Structure) dataset using mne/mne-bids, executed via `uv run` with no preinstalled environment required. Walks through directory scanning, subject/session/task/run entity parsing, per-recording conversion with correct sidecar metadata, participants.tsv/dataset_description.json generation, and BIDS-validator validation. Use this skill whenever the user wants to convert, BIDSify, restructure, or organize EEG data into BIDS format, prepare a raw EEG dataset for OpenNeuro/BIDS-Apps/sharing/publication, fix BIDS-validator errors on an EEG dataset, or mentions mne-bids, EEG-BIDS, or a folder of raw EEG recordings (EDF/GDF/BrainVision/etc.) that needs standardizing, even if they don't use the exact words "BIDS" or "convert".
---

# EEG to BIDS converter

Run the steps in order. Each one runs a script or makes one scoped decision.
The scripts handle everything mechanical. Your job is the part no script can
do: read the dataset's own documentation, and decide what its files and event
codes actually mean.

Three rules govern every step.

**Never modify the source dataset.** Read from it, write elsewhere. If
something in the source needs repairing to be readable, copy it to scratch and
repair the copy.

**Record what the dataset says, not what would look complete.** A
plausible-sounding guess is data corruption that no validator will catch. This
applies to sidecar fields, event labels, and column descriptions alike.

**Ask the user before falling back to `"n/a"`.** The order is: the dataset's
documentation, then the user, then `"n/a"`. Skipping the middle step throws
away real information. The user often knows the recording country, the lab,
the hardware, or what a trigger code meant, even when the dataset never wrote
it down. Ask when the answer changes the output and you cannot derive it. Do
not ask about anything you could read from the data or the docs yourself.

**When no user is reachable** (batch run, subagent, CI), the ladder is docs
then `"n/a"`, with nothing in between. Convention, plausibility, and what
similar datasets usually do are not sources. Log the question you would have
asked, and report it in Step 7.

Run any script with `--help` for its full arguments. This file covers when to
use which, not every flag.

## Situational references

Most conversions need none of these. Read one when you hit its situation. They
are not background reading.

| Situation | Read |
|---|---|
| `mne.io.read_raw` cannot open the file (custom `.mat`, proprietary binary) | `references/custom_formats.md` |
| Events are not already in `raw.annotations`, or you need to document trigger codes | `references/events.md` |
| The dataset says anything about electrode positions, or you want `--montage` | `references/electrodes.md` |
| The source ships already-filtered copies of the recordings | `references/derivatives.md` |
| You need a spec fact: entity rules, sidecar fields, column names, format quirks | `references/bids_reference.md` |
| You are writing a metadata file by hand, or want to see a finished one | `references/templates_and_examples.md` |

## Step 1: See what's there

```bash
uv run scripts/inspect_dataset.py <raw_root>
```

Lists every extension, which files are readable EEG recordings, and which look
like external event or metadata files. Then read the dataset's own
README/paper. That is where Steps 2 and 3 get their answers. If the local docs
only name a DOI or a landing page, follow it. That is usually where the
recording setup is written down.

**If the input is already a BIDS tree** (`dataset_description.json` plus
`sub-*/` at the root), this is not a conversion job. Run
`scripts/validate_bids.py` on it, report what it says, and ask the user what
they want. Re-converting an existing BIDS dataset into a second one is almost
never it. One exception: a `sourcedata/` folder holding the original raw
files. Convert from there, not from the BIDS tree.

Reading is delegated to `mne.io.read_raw`, so every format mne supports is
handled, including ones that look proprietary (`.cdt` Curry, `.mff` EGI,
`.lay` Persyst). **A format you don't recognise is not a format that needs a
custom parser.** Try `mne.io.read_raw` first. If it complains about a missing
package, install the package. Only once it genuinely cannot read the file, go
to `references/custom_formats.md`.

## Step 2: Map filenames to BIDS entities

Write a regex with named groups. Dry-run it before converting anything.

```bash
uv run scripts/inspect_dataset.py <raw_root> \
    --pattern '(?P<subject>P\d+)_(?P<task>[A-Za-z]+)' --out entities.json
```

Groups: `subject` (required), `session`, `task`, `run`, `acq`. Omit any the
dataset does not have. Do not invent `ses-01` for a dataset with no sessions.
Iterate until every recording maps to entities that read correctly, not merely
until the regex matches. Files that genuinely differ from the rest are fine as
documented exceptions.

This maps one file to one recording. If a single source file holds several
recordings, which is normal for `.mat`, the split happens in your loader
rather than in the regex. Read `references/custom_formats.md` before writing
that loader: it covers both the split and the check that the parse is
correct.

## Step 3: Collect what only the documentation and the user can answer

From the dataset's paper, README, or hardware manual. Never from memory of a
similar dataset. None of the following can be derived from the signal data, so
each is a decision somebody has to make.

- **Recording setup**: `PowerLineFrequency` (50/60, follows the recording
  country), `EEGReference`, `EEGGround`, `Manufacturer`,
  `ManufacturersModelName`, `CapManufacturer`, `EEGPlacementScheme`,
  `TaskDescription`, `InstitutionName`
- **Event semantics**: what each trigger code means. Undocumented codes keep
  their raw number in `value` and say so. Do not name them by guess.
- **Entity ambiguity**: when a filename token could be session or run, when
  subjects appear under two ID schemes, when tasks share a label
- **Electrode positions**: digitized for real, or only a named scheme?
- **Anonymization**: are recording dates identifiable?
- **Extra data**: preprocessed copies, unused channels, files whose role is
  not obvious. Keep, convert separately, or leave out?
- **Provenance**: authors, license, DOI, how the dataset should be cited

Take everything the documentation did not answer back to the user in one
batch. Not one question at a time, and not after the conversion is already
written. Say what you found, what you could not, and what you would otherwise
record as `"n/a"` or decide arbitrarily.

Whatever survives that conversation unanswered is genuinely `"n/a"`, and you
report it as such in Step 7. `convert_recording.py` prints which of these
fields are still unset after each write, so nothing goes missing just because
you stopped looking.

## Step 4: Convert each recording

```bash
uv run scripts/convert_recording.py \
    --input <raw_file> --bids-root <bids_root> \
    --subject <sub> [--session <ses>] --task <task> [--run <run>] \
    --line-freq <50|60> \
    [--channel-types '{"HEOG":"eog","ECG":"ecg"}'] \
    [--rename-channels '{...}'] [--drop-channels 'A,B'] \
    [--annotations-only | --events-csv <path> --events-descriptions '{...}'] \
    [--montage standard_1020] [--anonymize-daysback N] \
    --overwrite
```

Loop it over every recording. A shell or Python driver reading `entities.json`
is expected. What must not vary between recordings is the script call itself.

After each write the script re-reads the file it just produced and compares
sampling rate, duration, and waveform against the source. If that check fails,
the output does not contain the input. Fix it before continuing. Never work
around it. Its silence is the only evidence you have that the signal survived,
because the validator in Step 6 cannot tell you.

One thing it cannot cover: when you built the Raw yourself, it compares the
output against your parse, so both sides are wrong together and it stays
silent. A loader you wrote must check itself before writing. The three
assertions to use are in `references/custom_formats.md`.

**Events:** exactly one of `--annotations-only` (mne reads embedded
annotations) or `--events-csv` (a table you built). Neither, only if the
recording truly has no events. Anything beyond that:
`references/events.md`.

**Channel types:** EOG/ECG/trigger channels left as generic EEG produce a
wrong `channels.tsv`. mne infers type from the data, not from the name.

**`--montage`:** only when the recording used that layout AND you have real
measured positions. If you know the scheme but not the coordinates, skip the
flag and set `EEGPlacementScheme` in Step 5. A fabricated electrodes.tsv is a
spec violation. An absent one is fine. Details: `references/electrodes.md`.

**Output format:** BIDS accepts EDF, BrainVision, EEGLAB, and BDF. Anything
else is converted to BrainVision on write. That is expected. Its one
consequence is Step 5's.

**Preprocessed copies shipped by the source:** `references/derivatives.md`.
They must not go in the raw `sub-*/` tree, and must not be silently dropped.

## Step 5: Patch the facts from Step 3

```bash
uv run scripts/patch_sidecar.py --bids-root <bids_root> \
    --entries '{"EEGReference":"...","EEGGround":"...","Manufacturer":"..."}'
```

mne-bids leaves `EEGReference` and `EEGGround` as `"n/a"` because it cannot
know them.

`Manufacturer` is different, and worse. mne-bids fills it from the extension
of the file it *wrote*, so a Neuroscan recording converted to BrainVision
comes out claiming `"Brain Products"`. It is not `"n/a"`, so nothing flags it
as missing, and the validator has no opinion. `convert_recording.py` warns
whenever it converted the format. When it does, patch `Manufacturer` with the
hardware the documentation names, or `"n/a"` if it names none. The same
applies to `EEGPlacementScheme`, which the BrainVision writer fills with a
generic string.

Narrow with `--subject`/`--task` only if recordings genuinely differ.

## Step 6: Dataset metadata, then validate

Metadata **last**. `write_raw_bids` rewrites `participants.tsv` on every call,
so running this before Step 4 finishes silently discards it.

```bash
uv run scripts/write_bids_metadata.py --list-columns <demographics_file>   # if one exists

uv run scripts/write_bids_metadata.py \
    --bids-root <bids_root> --name "<name>" --authors "A,B" --license CC0 \
    [--doi <DatasetDOI> --references-and-links "<url>,<url>"] \
    [--how-to-acknowledge "<the source's own wording>" --funding "<grant>,<grant>"] \
    [--ethics-approvals "<approval reference>"] \
    [--demographics-file <path> --column-map '{"SubjID":"participant_id","Age":"age"}' \
     --column-descriptions '{"group":{"Description":"...","Levels":{...}}}'] \
    [--readme-text "$(cat readme.md)"]
```

`participants.json` is generated to describe exactly the columns that exist.
If the dataset has no demographics, that is a single `participant_id` entry
saying so. Do not reach for age/sex/handedness columns the source never
provided. Supply `--column-descriptions` for any non-standard column you
mapped, using the source's own definitions.

```bash
uv run scripts/validate_bids.py <bids_root> [--recursive]
```

Fix root causes and re-run until zero errors. Never silence an error to make
it pass. Warnings about genuinely-absent optional metadata are expected.

Lines prefixed `KEY` come from a second check, not from the official
validator. It compares your sidecar keys against `references/examples/`, a
hand-checked dataset, and reports misspellings and malformed data
dictionaries. The official validator ignores a key it does not recognise, so
a miscapitalized field is silently absent rather than reported wrong. Three
of four such defects passed it cleanly when measured.

**Zero errors is not "done".** The validator checks structure: filenames,
required fields, column names. It cannot see that a sidecar states hardware
the recording never used, that a trigger code was named by guess, or that the
samples were written in the wrong order. Conversions wrong in all three ways
have passed it cleanly. What makes a conversion finished is the Step 4
read-back check passing for every recording, and the Step 7 record being
honest. Not the validator's exit code.

## Step 7: Report

Tell the user what was converted, the validator result, and, most importantly,
every judgment call from Step 3 with its source. Include anything you
inferred, could not determine, or deliberately left out, and every question
you would have asked had a user been available. That list is what makes the
conversion auditable by someone who knows the data.
