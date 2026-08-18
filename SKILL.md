---
name: eeg-bids-converter
description: Converts arbitrary raw/messy EEG datasets (EDF, BrainVision, EEGLAB .set, Biosemi BDF, GDF, CNT, custom MATLAB .mat structs, or anything else mne can read or be coerced into) into a spec-valid BIDS (Brain Imaging Data Structure) dataset using mne/mne-bids, executed via `uv run` with no preinstalled environment required. Walks through directory scanning, subject/session/task/run entity parsing, per-recording conversion with correct sidecar metadata, participants.tsv/dataset_description.json generation, and BIDS-validator validation. Use this skill whenever the user wants to convert, BIDSify, restructure, or organize EEG data into BIDS format, prepare a raw EEG dataset for OpenNeuro/BIDS-Apps/sharing/publication, fix BIDS-validator errors on an EEG dataset, or mentions mne-bids, EEG-BIDS, or a folder of raw EEG recordings (EDF/GDF/BrainVision/etc.) that needs standardizing -- even if they don't use the exact words "BIDS" or "convert".
---

# EEG to BIDS converter

Run the steps in order. Each one either runs a script or makes one scoped
decision. The scripts handle everything mechanical; your job is the part no
script can do -- reading the dataset's own documentation and deciding what
its files and event codes actually mean.

Three rules that govern every step:

**Never modify the source dataset.** Read from it, write elsewhere. If
something in the source needs repairing to be readable, copy it to scratch
and repair the copy.

**Record what the dataset says, not what would look complete.** A
plausible-sounding guess is data corruption that no validator will catch.
This applies to sidecar fields, event labels, and column descriptions alike.

**Ask the user before falling back to `"n/a"`.** The order is: the
dataset's documentation, then the user, then `"n/a"`. Skipping the middle
step throws away real information -- the user often knows the recording
country, the lab, the hardware, or what a trigger code meant, even when the
dataset never wrote it down. `"n/a"` is the honest answer only once both
the docs and the user have come up empty. Ask when the answer changes the
output and you can't derive it; don't ask about anything you could read
from the data or the docs yourself.

Run any script with `--help` for its full arguments; this file covers when
to use which, not every flag.

## Step 1: See what's there

```bash
uv run scripts/inspect_dataset.py <raw_root>
```

Lists every extension, which files are readable EEG recordings, and which
look like external event/metadata files. Then read the dataset's own
README/paper -- that is where Steps 2 and 3 get their answers.

Reading is delegated to `mne.io.read_raw`, so every format mne supports is
handled -- including ones that look proprietary (`.cdt` Curry, `.mff` EGI,
`.lay` Persyst). **Verify a format is really unreadable before writing your
own parser for it**; a hand-written binary parser that guesses the sample
layout wrong produces a file that passes the BIDS validator with zero errors
and contains nothing but scrambled numbers. Only when mne genuinely cannot
read the file (usually a custom `.mat` layout) go to
`references/mne_bids_cookbook.md`.

## Step 2: Map filenames to BIDS entities

Write a regex with named groups and dry-run it before converting anything:

```bash
uv run scripts/inspect_dataset.py <raw_root> \
    --pattern '(?P<subject>P\d+)_(?P<task>[A-Za-z]+)' --out entities.json
```

Groups: `subject` (required), `session`, `task`, `run`, `acq`. Omit any the
dataset doesn't have -- don't invent `ses-01` for a dataset with no
sessions. Iterate until every recording maps to entities that read
correctly, not merely until the regex matches. Files that genuinely differ
from the rest are fine as documented exceptions.

## Step 3: Collect what only the documentation and the user can answer

From the dataset's paper, README, or hardware manual -- never from memory
of a similar dataset. None of the following can be derived from the signal
data, so each is a decision somebody has to make:

- **Recording setup**: `PowerLineFrequency` (50/60, follows the recording
  country), `EEGReference`, `EEGGround`, `Manufacturer`,
  `ManufacturersModelName`, `CapManufacturer`, `EEGPlacementScheme`
- **Event semantics**: what each trigger code means. Undocumented codes
  keep their raw number in `value` and say so; don't name them by guess.
- **Entity ambiguity**: when a filename token could be session or run,
  when subjects appear under two ID schemes, when tasks share a label
- **Electrode positions**: digitized for real, or only a named scheme?
- **Anonymization**: are recording dates identifiable?
- **Extra data**: preprocessed copies, unused channels, files whose role
  isn't obvious -- keep, convert separately, or leave out?
- **Provenance**: authors, license, how the dataset should be cited

Take everything the documentation didn't answer back to the user in one
batch -- not one question at a time, and not after the conversion is
already written. Say what you found, what you couldn't, and what you'd
otherwise record as `"n/a"` or decide arbitrarily. The user frequently
knows what the dataset never wrote down: the recording country, the lab,
which files matter, what a trigger code meant.

Whatever survives that conversation unanswered is genuinely `"n/a"`, and
you report it as such in Step 7. `convert_recording.py` prints which of
these fields are still unset after each write, so nothing goes missing
just because you stopped looking.

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

Loop it over every recording (a shell/Python driver reading `entities.json`
is expected). What must not vary between recordings is the script call
itself.

**Events:** exactly one of `--annotations-only` (mne reads embedded
annotations) or `--events-csv` (you built an onset/duration/trial_type
table -- see the cookbook). Neither, only if the recording truly has no
events. With `--events-csv` always pass `--events-descriptions` giving
`Description` and `Levels` for the codes you decoded in Step 3; nothing
else writes that events.json.

**Channel types:** EOG/ECG/trigger channels left as generic EEG produce a
wrong `channels.tsv`. mne infers type from the data, not the name.

**`--montage`:** only when the recording genuinely used that layout. If you
know the scheme but not real digitized positions, skip it and set
`EEGPlacementScheme` in Step 5 instead. A fabricated electrodes.tsv is a
spec violation; an absent one is fine.

**Custom formats:** build a Raw, save `.fif`, pass it with `--format fif`
(cookbook). Same script, same write path.

## Step 4b: Source-provided preprocessed data

If the source ships an already-filtered copy alongside the raw data, it must
not go in the raw `sub-*/` tree -- BIDS raw means minimally processed. Put
it in a derivatives dataset, or skip it and say so in Step 7. Silently
dropping it is the one option that isn't acceptable.

```bash
uv run scripts/convert_recording.py --input <processed_file> \
    --bids-root <bids_root>/derivatives/<pipeline> \
    --subject <sub> --task <task> --desc preproc --line-freq <50|60> --overwrite

uv run scripts/write_bids_metadata.py \
    --bids-root <bids_root>/derivatives/<pipeline> \
    --name "<dataset name> (<pipeline>)" --authors "<same as raw>" \
    --dataset-type derivative --generated-by-name <pipeline> \
    --generated-by-description "<what the source says was done>"
```

Record the actual filter settings in `SoftwareFilters` via Step 5. Validate
with `--recursive` in Step 6, or derivatives go unchecked.

## Step 5: Patch the facts from Step 3

```bash
uv run scripts/patch_sidecar.py --bids-root <bids_root> \
    --entries '{"EEGReference":"...","EEGGround":"...","Manufacturer":"..."}'
```

mne-bids writes these as `"n/a"` because it cannot know them. Narrow with
`--subject`/`--task` etc. only if recordings genuinely differ.

## Step 6: Dataset metadata, then validate

Metadata **last** -- `write_raw_bids` rewrites `participants.tsv` on every
call, so running this before Step 4 finishes silently discards it.

```bash
uv run scripts/write_bids_metadata.py --list-columns <demographics_file>   # if one exists

uv run scripts/write_bids_metadata.py \
    --bids-root <bids_root> --name "<name>" --authors "A,B" --license CC0 \
    [--demographics-file <path> --column-map '{"SubjID":"participant_id","Age":"age"}' \
     --column-descriptions '{"group":{"Description":"...","Levels":{...}}}'] \
    [--readme-text "$(cat readme.md)"]
```

`participants.json` is generated to describe exactly the columns that exist.
If the dataset has no demographics, that is a single `participant_id` entry
saying so -- don't reach for age/sex/handedness columns the source never
provided. Supply `--column-descriptions` for any non-standard column you
mapped, using the source's own definitions.

A good README states what was recorded, the task/paradigm, the source URL,
known issues, and anything you inferred rather than read. The spec mandates
no structure, so the useful content is whatever the machine-readable
sidecars can't express.

```bash
uv run scripts/validate_bids.py <bids_root> [--recursive]
```

Fix root causes and re-run until zero errors. Never silence an error to make
it pass. Warnings about genuinely-absent optional metadata are expected.

## Step 7: Report

Tell the user what was converted, the validator result, and -- most
importantly -- every judgment call from Step 3 with its source, plus
anything you inferred, couldn't determine, or deliberately left out. That
list is what makes the conversion auditable by someone who knows the data.

## References

- `references/bids_eeg_spec.md` -- entity rules, required/recommended sidecar fields, channels/events columns, derivatives requirements.
- `references/mne_bids_cookbook.md` -- custom formats, .mat loading, event construction, per-format gotchas.
