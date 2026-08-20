# BIDS-EEG reference

Condensed from official BIDS Specification (bids-specification.readthedocs.io,
stable/v1.11.1) and BIDS Validator docs. Lookup table, not read-start-to-end. Jump to section needed.

Situation-specific guidance elsewhere: `events.md`, `electrodes.md`,
`derivatives.md`, `custom_formats.md`. Finished spec-valid files to copy: `examples/`.

## Contents
- [Filenames and entities](#filenames-and-entities)
- [Top-level dataset files](#top-level-dataset-files)
- [Data dictionaries (any `.json` describing a `.tsv`)](#data-dictionaries-any-json-describing-a-tsv)
- [`*_eeg.json` sidecar fields](#_eegjson-sidecar-fields)
- [`*_channels.tsv`](#_channelstsv)
- [Allowed raw file formats](#allowed-raw-file-formats)
- [Per-format gotchas](#per-format-gotchas)
- [BIDS validator](#bids-validator)

## Filenames and entities

```
sub-<label>/[ses-<label>/]eeg/
    sub-<label>[_ses-<label>]_task-<label>[_acq-<label>][_run-<index>]_eeg.<ext>
```

| Entity | Key | Required for EEG |
|---|---|---|
| Subject | `sub-<label>` | REQUIRED |
| Session | `ses-<label>` | optional |
| Task | `task-<label>` | REQUIRED |
| Acquisition | `acq-<label>` | optional (e.g. positions recorded with different device) |
| Run | `run-<index>` | optional |

Rules:
- Entities in order above. Each entity max once per filename.
- Labels/indices alphanumeric only. No underscores, hyphens, spaces. `scripts/inspect_dataset.py --pattern` sanitizes captured values.
- `TaskName` in sidecar and `task-<label>` filename component can differ. Filename label = `TaskName` with non-alphanumeric chars stripped. `TaskName: "faces n-back"` → `task-facesnback`.
- Labels case-sensitive but must not collide case-insensitively. `sub-s1` and `sub-S1` can't coexist.
- `run-<index>` not zero-padded for you. Pass `--run 01`, not `--run 1`, else `run-1`/`run-10` sort wrong next to each other.
- Sidecars for one recording share its stem: `_eeg.json`, `_events.tsv` + `_events.json`, `_channels.tsv`, optionally `_electrodes.tsv` + `_coordsystem.json`.

## Top-level dataset files

**`dataset_description.json`** (root, REQUIRED)
- REQUIRED: `Name`, `BIDSVersion`
- RECOMMENDED: `DatasetType` (raw/derivative/study, default raw), `License`, `Authors`, `GeneratedBy`, `SourceDatasets`, `HEDVersion` (only if some `*_events.json` in the dataset carries a `HED` field — this skill doesn't generate HED tags, so leave it out unless the source data already has them)
- OPTIONAL: `DatasetLinks`, `Keywords`, `Acknowledgements`, `HowToAcknowledge`, `Funding`, `EthicsApprovals`, `ReferencesAndLinks`, `DatasetDOI`
- Written by `scripts/write_bids_metadata.py` via `mne_bids.make_dataset_description()`.

**`participants.tsv` + `participants.json`** (root, RECOMMENDED, expected in practice)
- `participant_id` (format `sub-<label>`) REQUIRED, first column, one row per participant.
- Recommended columns: `age`, `sex`, `handedness`, `species`, `strain`, `strain_rrid`.
- Privacy: top-code ages, commonly capped at 89.
- `participants.json` must describe exactly columns present. Documenting column TSV lacks worse than documenting nothing.

**`README`** (root, REQUIRED). ASCII/UTF-8, exactly one of `README`, `README.md`,
`README.rst`, `README.txt`. Spec mandates no structure, only "SHOULD describe dataset
in more detail" and stay readable unrendered. Useful content: what machine-readable
sidecars can't express — what recorded and why, paradigm, known data-quality issues,
source URL, anything inferred rather than read.

**`CHANGES`** (root, OPTIONAL). Changelog, ASCII/UTF-8.

## Data dictionaries (any `.json` describing a `.tsv`)

Every column name maps to **one object**, never array. Keys PascalCase: `LongName`,
`Description`, `Format`, `Levels`, `Units`, `Delimiter`, `TermURL`, `HED`, `Minimum`, `Maximum`.

```json
{
  "age": {"Description": "Age of the participant", "Units": "years"},
  "group": {
    "Description": "Study group",
    "Levels": {"ctrl": "Healthy control", "pat": "Clinical group"}
  }
}
```

`"age": [{...}]` and `"levels"` lowercase both wrong, both common. Validator doesn't
always object — check shape, don't assume.

## `*_eeg.json` sidecar fields

**REQUIRED**: `TaskName`, `EEGReference`, `SamplingFrequency`,
`PowerLineFrequency` (number, or `"n/a"` only if genuinely unknown),
`SoftwareFilters` (object, or `"n/a"` if none).

**RECOMMENDED**: `CapManufacturer`, `CapManufacturersModelName`,
`EEGChannelCount`, `ECGChannelCount`, `EMGChannelCount`, `EOGChannelCount`,
`MiscChannelCount`, `TriggerChannelCount`, `RecordingDuration`,
`RecordingType` (`continuous`/`epoched`/`discontinuous`), `EpochLength`,
`EEGGround`, `HeadCircumference`, `EEGPlacementScheme`, `HardwareFilters`,
`SubjectArtefactDescription`, `Manufacturer`, `ManufacturersModelName`,
`SoftwareVersions`, `DeviceSerialNumber`, `TaskDescription`, `Instructions`,
`CogAtlasID`, `CogPOID`, `InstitutionName`, `InstitutionAddress`,
`InstitutionalDepartmentName`.

**OPTIONAL**: `ElectricalStimulation` (boolean),
`ElectricalStimulationParameters` (string).

Types matter. `RecordingDuration` number, not `"1834.8"`.
`ElectricalStimulation` boolean, not `"True"`.

Misc channel count = `MiscChannelCount`. `MISCChannelCount` deprecated alias, still
shows in older docs tables, but schema marks deprecated — new datasets SHOULD use
`MiscChannelCount`.

`write_raw_bids()` auto-fills `SamplingFrequency` + `*ChannelCount` fields from
`raw.info`, sometimes infers `EEGPlacementScheme` from standard channel names.
Can't infer `EEGReference` or `EEGGround`. Fix `PowerLineFrequency` by setting
`raw.info["line_freq"]` before writing (`convert_recording.py --line-freq`). Rest
needs `scripts/patch_sidecar.py` after.

**`Manufacturer` written from output extension**, not hardware: `.vhdr` gives
"Brain Products", `.bdf` "Biosemi", `.cdt` "Curry", `.fif` "Elekta", `.edf`/`.set`
"n/a". SKILL.md Step 5 covers fix.

## `*_channels.tsv`

REQUIRED columns, in order: `name` (unique), `type` (restricted vocab, UPPERCASE),
`units` (SI, e.g. `V`).

Allowed `type` values: `AUDIO`, `EEG`, `EOG`, `ECG`, `EMG`, `EYEGAZE`, `GSR`,
`HEOG`, `MISC`, `PPG`, `PUPIL`, `REF`, `RESP`, `SYSCLOCK`, `TEMP`, `TRIG`,
`VEOG`.

Optional columns: `description`, `sampling_frequency`, `reference`,
`low_cutoff`, `high_cutoff`, `notch`, `status` (good/bad),
`status_description`.

`type` comes from MNE channel type set via `raw.set_channel_types(...)` before
writing (`convert_recording.py --channel-types`), not from channel name.

## Allowed raw file formats

RECOMMENDED: **EDF** (`.edf`), **BrainVision** (`.vhdr` + `.vmrk` + `.eeg`).
Permitted but discouraged: **EEGLAB** (`.set`, optional `.fdt`), **Biosemi BDF** (`.bdf`).

**Extensions must be lowercase.** Spec: capital `.EDF`/`.BDF` MUST NOT be used.
Source file named `.EDF` reads fine, but name can't carry into BIDS tree.
`edf+`/`bdf+` files permitted.

Everything else (GDF, CNT, Curry, FIF, custom) converted to BrainVision on write.
Normal, not data-quality problem — but `Manufacturer` trap above applies, output
format won't match source's.

## Per-format gotchas

**BrainVision** triplet (`.vhdr` + `.eeg` + `.vmrk`) where `.vhdr` names siblings
internally. Reorganizing archive renames files but not pointers — mne fails with
confusing "file not found". `convert_recording.py` detects, warns. Fix: copy
triplet to scratch, correct pointers *there*. Never edit source dataset files.

**EDF** stores 16-bit samples against one physical range shared by all channels —
single high-amplitude channel coarsens rest. Vs BrainVision on real data: EDF
costs ~60-85 dB. Also pads recording to whole number of one-second data records,
appending up to 1s flat fabricated signal, changing `RecordingDuration`, truncates
channel names at 16 chars. Long channel names / wide dynamic range → write
BrainVision instead (`--output-format BrainVision`).

**BDF** valid BIDS format, not valid explicit `format=` target for mne-bids. Any
channel edit forces preload → forces explicit format, so edited BDF source comes
out as BrainVision. Expected.

**EEGLAB** `.set` is header only. Samples live in sibling `.fdt`. mne-bids'
copy-through path writes only `.set` — output reads back "`..._eeg.fdt` not found"
while validator reports zero errors. `convert_recording.py` preloads `.set`
sources, writes single self-contained `.set` to avoid this.

Tell two apart by size, not assumption. Self-contained `.set` roughly source
`.set` + `.fdt` combined size (now holds samples). Output `.set` still header
size — e.g. 11 MB where source `.fdt` was 373 MB — is broken case. No format
conversion/compression/resampling explains it: `write_raw_bids` does none. Open
output, check it reads.

Also: `read_raw_eeglab` falls back to same-stem `.fdt` when header names
nonexistent file — stale internal pointer usually needs no repair.

**Curry** (`.cdt` plus `.cdt.dpa`/`.cdt.ceo`) reads natively via
`mne.io.read_raw_curry`, needs `curryreader` package. Missing package ≠
unsupported format.

**GDF and CNT** not BIDS formats. Always converted on write. `.cnt` used by both
Neuroscan (`read_raw_cnt`) and ANT Neuro eego (`read_raw_ant`). Channels garbled →
check vendor guess first.

**Anonymization.** For real recording dates, pass `--anonymize-daysback N`
consistently across every recording in dataset. Applying to some not others worse
than not doing at all — implies guarantee dataset lacks. `raw.set_meas_date(None)`
drops date entirely, other common choice.

## BIDS validator

`scripts/validate_bids.py` wraps `bids-validator-deno` PyPI package, self-contained,
installed on demand by `uv run`. Exits nonzero only on real errors. Warnings printed,
don't fail run.

Checks structure, not signal. SKILL.md Step 6 covers what that leaves unchecked.