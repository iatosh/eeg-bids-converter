# BIDS-EEG reference

Condensed from the official BIDS Specification (bids-specification.readthedocs.io,
stable/v1.11.1) and BIDS Validator docs. A lookup table, not something to read
start to end. Jump to the section you need.

Situation-specific guidance lives elsewhere: `events.md`, `electrodes.md`,
`derivatives.md`, `custom_formats.md`. Finished spec-valid files to copy from:
`examples/`.

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
| Acquisition | `acq-<label>` | optional (e.g. positions recorded with a different device) |
| Run | `run-<index>` | optional |

Rules:
- Entities appear in the order above. Each entity at most once per filename.
- Labels and indices are **alphanumeric only**. No underscores, hyphens, spaces. `scripts/inspect_dataset.py --pattern` sanitizes captured values for you.
- `TaskName` in the sidecar and the `task-<label>` filename component can differ. The filename label is `TaskName` with all non-alphanumeric characters stripped. `TaskName: "faces n-back"` gives `task-facesnback`.
- Labels are case-sensitive but must not collide case-insensitively. `sub-s1` and `sub-S1` cannot coexist.
- `run-<index>` is not zero-padded for you. Pass `--run 01`, not `--run 1`, or `run-1` and `run-10` sort wrongly next to each other.
- Sidecars for one recording share its stem: `_eeg.json`, `_events.tsv` + `_events.json`, `_channels.tsv`, optionally `_electrodes.tsv` + `_coordsystem.json`.

## Top-level dataset files

**`dataset_description.json`** (root, REQUIRED)
- REQUIRED: `Name`, `BIDSVersion`
- RECOMMENDED: `DatasetType` (raw/derivative/study, default raw), `License`, `Authors`, `GeneratedBy`, `SourceDatasets`, `HEDVersion`
- OPTIONAL: `DatasetLinks`, `Keywords`, `Acknowledgements`, `HowToAcknowledge`, `Funding`, `EthicsApprovals`, `ReferencesAndLinks`, `DatasetDOI`
- Written by `scripts/write_bids_metadata.py` via `mne_bids.make_dataset_description()`.

**`participants.tsv` + `participants.json`** (root, RECOMMENDED, expected in practice)
- `participant_id` (format `sub-<label>`) REQUIRED, first column, one row per participant.
- Recommended columns: `age`, `sex`, `handedness`, `species`, `strain`, `strain_rrid`.
- Privacy: top-code ages, commonly capped at 89.
- `participants.json` must describe exactly the columns present. Documenting a column the TSV does not have is worse than documenting nothing.

**`README`** (root, REQUIRED). ASCII/UTF-8, exactly one of `README`, `README.md`,
`README.rst`, `README.txt`. The spec mandates no structure, only that it
"SHOULD describe the dataset in more detail" and stay readable unrendered. So
the useful content is whatever the machine-readable sidecars cannot express:
what was recorded and why, the paradigm, known data-quality issues, the source
URL, and anything you inferred rather than read.

**`CHANGES`** (root, OPTIONAL). Changelog, ASCII/UTF-8.

## Data dictionaries (any `.json` describing a `.tsv`)

Every column name maps to **one object**, never to an array. Keys are
PascalCase: `LongName`, `Description`, `Format`, `Levels`, `Units`,
`Delimiter`, `TermURL`, `HED`, `Minimum`, `Maximum`.

```json
{
  "age": {"Description": "Age of the participant", "Units": "years"},
  "group": {
    "Description": "Study group",
    "Levels": {"ctrl": "Healthy control", "pat": "Clinical group"}
  }
}
```

`"age": [{...}]` and `"levels"` lowercase are both wrong and both common. The
validator does not always object, so check the shape rather than assuming.

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

Types matter. `RecordingDuration` is a number, not `"1834.8"`.
`ElectricalStimulation` is a boolean, not `"True"`.

The misc channel count is `MiscChannelCount`. `MISCChannelCount` exists as a
deprecated alias, and older documentation tables still show it, but the schema
marks it deprecated and says new datasets SHOULD use `MiscChannelCount`.

`write_raw_bids()` auto-fills `SamplingFrequency` and the `*ChannelCount`
fields from `raw.info`, and sometimes infers `EEGPlacementScheme` from
standard channel names. It cannot infer `EEGReference` or `EEGGround`.
`PowerLineFrequency` you fix by setting `raw.info["line_freq"]` before writing
(`convert_recording.py --line-freq`). The rest need
`scripts/patch_sidecar.py` afterwards.

**`Manufacturer` is a trap.** mne-bids fills it from a lookup on the file
extension it *wrote*: `.vhdr` gives "Brain Products", `.bdf` gives "Biosemi",
`.cdt` gives "Curry", `.fif` gives "Elekta". That names the vendor of the file
format, not the amplifier. Any recording whose format was converted on write
ends up asserting hardware it was never recorded on, with a value that is not
`"n/a"` and so passes every emptiness check. `convert_recording.py` prints a
warning whenever it converted the format. Overwrite the value with the real
one from the dataset's documentation.

## `*_channels.tsv`

REQUIRED columns, in order: `name` (unique), `type` (restricted vocabulary,
UPPERCASE), `units` (SI, e.g. `V`).

Allowed `type` values: `AUDIO`, `EEG`, `EOG`, `ECG`, `EMG`, `EYEGAZE`, `GSR`,
`HEOG`, `MISC`, `PPG`, `PUPIL`, `REF`, `RESP`, `SYSCLOCK`, `TEMP`, `TRIG`,
`VEOG`.

Optional columns: `description`, `sampling_frequency`, `reference`,
`low_cutoff`, `high_cutoff`, `notch`, `status` (good/bad),
`status_description`.

`type` comes from the MNE channel type set via `raw.set_channel_types(...)`
before writing (`convert_recording.py --channel-types`), not from the channel
name.

## Allowed raw file formats

RECOMMENDED: **EDF** (`.edf`), **BrainVision** (`.vhdr` + `.vmrk` + `.eeg`).
Permitted but discouraged over those two: **EEGLAB** (`.set`, optional
`.fdt`), **Biosemi BDF** (`.bdf`).

**Extensions must be lowercase.** The spec states the capital `.EDF` and
`.BDF` forms MUST NOT be used. A source file named `.EDF` reads fine, but the
name cannot be carried into the BIDS tree. `edf+` and `bdf+` files are
permitted.

Everything else (GDF, CNT, Curry, FIF, custom) is converted to BrainVision on
write. That is normal and not a data-quality problem, but it does mean the
`Manufacturer` trap above applies, and the output format will not match the
source's.

## Per-format gotchas

**BrainVision** is a triplet (`.vhdr` + `.eeg` + `.vmrk`) where the `.vhdr`
names its siblings internally. Reorganizing an archive renames files but not
those pointers, and mne then fails with a confusing "file not found".
`convert_recording.py` detects this and says so. Fix it by copying the triplet
to scratch and correcting the pointers *there*. Never edit files in the source
dataset.

**EDF** stores 16-bit samples against one physical range shared by all
channels, so a single high-amplitude channel coarsens the rest. Measured
against BrainVision on real data, EDF costs roughly 60 to 85 dB. It also pads
the recording out to a whole number of one-second data records, appending up
to 1 s of flat fabricated signal and changing `RecordingDuration`, and it
truncates channel names at 16 characters. For long channel names or wide
dynamic range, write BrainVision instead (`--output-format BrainVision`).

**BDF** is a valid BIDS format but not a valid explicit `format=` target for
mne-bids. Any channel edit forces a preload, which forces an explicit format,
so an edited BDF source comes out as BrainVision. That is expected.

**EEGLAB** `.set` is a header. The samples live in a sibling `.fdt`.
mne-bids' copy-through path writes only the `.set`, producing an output that
reads back as "`..._eeg.fdt` not found" while the validator reports zero
errors. `convert_recording.py` preloads `.set` sources and writes a single
self-contained `.set` to avoid this.

Tell the two apart by size, not by assuming the fix applied. A self-contained
`.set` is roughly as large as the source `.set` plus `.fdt` together, because
it now holds the samples. An output `.set` still at header size, 11 MB where
the source `.fdt` was 373 MB, is the broken case. No amount of format
conversion, compression, or resampling explains it: `write_raw_bids` does
neither. Open the output and check it reads.

Also: `read_raw_eeglab` falls back to the same-stem `.fdt` when the header
names a file that does not exist, so a stale internal pointer usually needs no
repair.

**Curry** (`.cdt` plus `.cdt.dpa`/`.cdt.ceo`) reads natively via
`mne.io.read_raw_curry`, which needs the `curryreader` package. A missing
package is not the same as an unsupported format.

**GDF and CNT** are not BIDS formats. They always get converted on write.
`.cnt` is used by both Neuroscan (`read_raw_cnt`) and ANT Neuro eego
(`read_raw_ant`). If channels come out garbled, the vendor guess is the first
thing to check.

**Anonymization.** For real recording dates, pass `--anonymize-daysback N`
consistently across every recording in the dataset. Applying it to some and
not others is worse than not doing it at all: it implies a guarantee the
dataset does not have. `raw.set_meas_date(None)` drops the date entirely and
is the other common choice.

## BIDS validator

`scripts/validate_bids.py` wraps the `bids-validator-deno` PyPI package,
self-contained and installed on demand by `uv run`. It exits nonzero only on
real errors. Warnings are printed but do not fail the run.

**Zero errors does not mean the conversion is correct.** The validator checks
structure: filenames, required fields, column names. It cannot check that the
signal in the output is the signal that was in the input, or that
`EEGReference` says what the hardware actually did. Every silent corruption
found while testing this skill passed it with zero errors.
