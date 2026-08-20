---
name: eeg-bids-converter
description: Converts arbitrary raw/messy EEG datasets (EDF, BrainVision, EEGLAB .set, Biosemi BDF, GDF, CNT, Curry .cdt, custom MATLAB .mat structs, or anything else mne can read or be coerced into) into a spec-valid BIDS (Brain Imaging Data Structure) dataset using mne/mne-bids, executed via `uv run` with no preinstalled environment required. Walks through directory scanning, subject/session/task/run entity parsing, per-recording conversion with correct sidecar metadata, participants.tsv/dataset_description.json generation, and BIDS-validator validation. Use this skill whenever the user wants to convert, BIDSify, restructure, or organize EEG data into BIDS format, prepare a raw EEG dataset for OpenNeuro/BIDS-Apps/sharing/publication, fix BIDS-validator errors on an EEG dataset, or mentions mne-bids, EEG-BIDS, or a folder of raw EEG recordings (EDF/GDF/BrainVision/etc.) that needs standardizing, even if they don't use the exact words "BIDS" or "convert".
---
# BIDS converter for EEG

Run steps in order. Each runs script or makes one scoped decision.
Scripts handle mechanical part. Your job: part no script can do — read dataset's own docs, decide what files and event codes mean.

Three rules govern every step.

**Never modify source dataset.** Read from it, write elsewhere. Something in source needs repair to be readable? Copy to scratch, repair copy.

**Record what dataset says, not what looks complete.** Plausible-sounding guess = data corruption no validator catches. Applies to sidecar fields, event labels, column descriptions alike.

**Ask user before falling back to `"n/a"`.** Order: dataset's documentation, then user, then `"n/a"`. Skip middle step = throw away real info. User often knows recording country, lab, hardware, what trigger code meant — even when dataset never wrote it down. Ask when answer changes output and you can't derive it. Don't ask what you could read from data or docs yourself.

**No user reachable** (batch run, subagent, CI): ladder is docs then `"n/a"`, nothing between. Convention, plausibility, what similar datasets usually do — not sources. Log question you would've asked, report in Step 7.

Run any script with `--help` for full args. This file covers when to use which, not every flag.

## Prerequisite: a runner

Every command below written `uv run scripts/<name>.py`. Scripts carry PEP 723 dependency blocks — uv installs what each needs on first use.
Check before Step 1:

```bash
uv --version
```

Fails? Stop, put choice to user. Install nothing yourself:

- **uv** (<https://docs.astral.sh/uv/>), then run everything as written.
- **Existing Python** 3.10+, with scripts' dependencies installed into it, then `python3` in place of `uv run` throughout. Install with:

```bash
pip install "mne>=1.6" "mne-bids>=0.14" "pybv>=0.7.3" \
    pandas openpyxl edfio eeglabio curryreader bids-validator-deno
```

Until one done, don't do script's work by hand instead. Every script here exists because that work has way to get silently wrong.

## Situational references

Most conversions need none of these. Read one when you hit its situation. Not background reading.

| Situation | Read |
|---|---|
| `mne.io.read_raw` cannot open file (custom `.mat`, proprietary binary) | `references/custom_formats.md` |
| Events not already in `raw.annotations`, or need to document trigger codes | `references/events.md` |
| Dataset says anything about electrode positions, or want `--montage` | `references/electrodes.md` |
| Source ships already-filtered copies of recordings | `references/derivatives.md` |
| Need spec fact: entity rules, sidecar fields, column names, format quirks | `references/bids_reference.md` |
| Writing metadata file by hand, or want to see finished one | `references/templates_and_examples.md` |

## Step 1: See what's there

```bash
uv run scripts/inspect_dataset.py <raw_root>
```

Lists every extension, which files readable EEG recordings, which look like external event or metadata files. Then read dataset's own README/paper — that's where Steps 2 and 3 get answers. Local docs only name DOI or landing page? Follow it — usually where recording setup written down.

**If input already BIDS tree** (`dataset_description.json` plus `sub-*/` at root), this isn't conversion job. Run `scripts/validate_bids.py` on it, report what it says, ask user what they want. Re-converting existing BIDS dataset into second one almost never it. One exception: `sourcedata/` folder holding original raw files — convert from there, not from BIDS tree.

Reading delegated to `mne.io.read_raw`, so every format mne supports handled, including proprietary-looking ones (`.cdt` Curry, `.mff` EGI, `.lay` Persyst). **Format you don't recognize isn't format needing custom parser.** Try `mne.io.read_raw` first. Complains about missing package? Install package. Only once it genuinely can't read file, go to `references/custom_formats.md`.

## Step 2: Map filenames to BIDS entities

Write regex with named groups. Dry-run before converting anything.

```bash
uv run scripts/inspect_dataset.py <raw_root> \
    --pattern '(?P<subject>P\d+)_(?P<task>[A-Za-z]+)' --out entities.json
```

Groups: `subject` (required), `session`, `task`, `run`, `acq`. Omit ones dataset lacks. Don't invent `ses-01` for dataset with no sessions. Iterate until every recording maps to entities reading correctly, not merely until regex matches. Files genuinely differing from rest — fine as documented exceptions.

Maps one file to one recording. Single source file holds several recordings (normal for `.mat`)? Split happens in your loader, not regex. Read `references/custom_formats.md` before writing that loader — covers split and check that parse correct.

## Step 3: Collect what only documentation and user can answer

From dataset's paper, README, hardware manual. Never from memory of similar dataset. None of following derivable from signal data — each decision somebody has to make.

- **Recording setup**: `PowerLineFrequency` (50/60, follows recording country), `EEGReference`, `EEGGround`, `Manufacturer`,
  `ManufacturersModelName`, `CapManufacturer`, `EEGPlacementScheme`,
  `TaskDescription`, `InstitutionName`
- **Event semantics**: what each trigger code means. Undocumented codes keep raw number in `value`, say so. Don't name by guess.
- **Entity ambiguity**: filename token could be session or run, subjects appear under two ID schemes, tasks share label
- **Electrode positions**: digitized for real, or only named scheme?
- **Anonymization**: recording dates identifiable?
- **Extra data**: preprocessed copies, unused channels, files whose role not obvious. Keep, convert separately, or leave out?
- **Provenance**: authors, license, DOI, how dataset should be cited

Take everything documentation didn't answer back to user in one batch. Not one question at time, not after conversion already written. Say what found, what couldn't, what you'd otherwise record as `"n/a"` or decide arbitrarily.

Whatever survives that conversation unanswered = genuinely `"n/a"`, report as such in Step 7. `convert_recording.py` prints which of these fields still unset after each write — nothing goes missing just because you stopped looking.

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

Loop over every recording. Shell or Python driver reading `entities.json` expected. What must not vary between recordings: script call itself.

After each write, script re-reads file, compares sampling rate, duration, waveform against source. Fails? Output doesn't contain input — fix it, never work around it. Its silence only evidence signal survived, since Step 6's validator can't tell you.

Can't cover Raw you built yourself, since then it compares your parse against your parse. Loader you wrote must check itself first — three assertions in `references/custom_formats.md`.

**Events:** exactly one of `--annotations-only` (mne reads embedded annotations) or `--events-csv` (table you built). Neither, only if recording truly has no events. Anything beyond that: `references/events.md`.

**Channel types:** EOG/ECG/trigger channels left as generic EEG produce wrong `channels.tsv`. mne infers type from data, not name.

**`--montage`:** only when recording used that layout AND you have real measured positions. Know scheme but not coordinates? Skip flag, set `EEGPlacementScheme` in Step 5. Fabricated electrodes.tsv = spec violation. Absent one fine. Details: `references/electrodes.md`.

**Output format:** BIDS accepts EDF, BrainVision, EEGLAB, BDF. Anything else converted to BrainVision on write — expected. One consequence: Step 5's.

**Preprocessed copies shipped by source:** `references/derivatives.md`. Must not go in raw `sub-*/` tree, must not be silently dropped.

## Step 5: Patch facts from Step 3

```bash
uv run scripts/patch_sidecar.py --bids-root <bids_root> \
    --entries '{"EEGReference":"...","EEGGround":"...","Manufacturer":"..."}'
```

mne-bids leaves `EEGReference` and `EEGGround` as `"n/a"` since it can't know them.

`Manufacturer` different, worse. mne-bids fills it from extension of file it *wrote* — Neuroscan recording converted to BrainVision comes out claiming `"Brain Products"`. Not `"n/a"`, so nothing flags it missing, validator has no opinion. `convert_recording.py` warns whenever it converted format. When it does, patch `Manufacturer` with hardware documentation names, or `"n/a"` if it names none. Same applies to `EEGPlacementScheme`, which BrainVision writer fills with generic string.

Narrow with `--subject`/`--task` only if recordings genuinely differ.

## Step 6: Dataset metadata, then validate

Metadata **last**. `write_raw_bids` rewrites `participants.tsv` on every call — running this before Step 4 finishes silently discards it.

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

`participants.json` generated to describe exactly columns that exist. Dataset has no demographics? Single `participant_id` entry saying so. Don't reach for age/sex/handedness columns source never provided. Supply `--column-descriptions` for any non-standard column you mapped, using source's own definitions.

```bash
uv run scripts/validate_bids.py <bids_root> [--recursive]
```

Fix root causes, re-run until zero errors. Never silence error to make it pass. Warnings about genuinely-absent optional metadata expected.

Lines prefixed `KEY` come from second check, not official validator. Compares your sidecar keys against `references/examples/`, hand-checked dataset, reports misspellings and malformed data dictionaries. Official validator ignores key it doesn't recognize — miscapitalized field silently absent rather than reported wrong. Three of four such defects passed it cleanly when measured.

**Zero errors isn't "done".** Validator checks structure: filenames, required fields, column names. Can't see sidecar states hardware recording never used, trigger code named by guess, samples written in wrong order. Conversions wrong all three ways have passed it cleanly. What makes conversion finished: Step 4 read-back check passing for every recording, Step 7 record being honest. Not validator's exit code.

## Step 7: Report

Tell user what converted, validator result, and — most important — every judgment call from Step 3 with its source. Include anything inferred, couldn't determine, or deliberately left out, and every question you would've asked had user been available. That list makes conversion auditable by someone who knows data.