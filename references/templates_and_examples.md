# Templates and worked example

Two dirs, same layout, different jobs.

**`templates/`** is what copy. Every value placeholder stating requirement level, type, what field for:

```json
"PowerLineFrequency": "<REQUIRED | number | 50 or 60, follows the recording country>",
"RecordingDuration": "<RECOMMENDED | number | seconds. A number, not a quoted string>",
```

Dir names carry layout too: `sub-<label>/eeg/`, `sub-<label>_task-<label>_eeg.json`. Copy tree, rename entities, replace placeholders.

**`examples/`** is what filled-in result looks like. Real one-subject dataset `validate_bids.py` reports 0 errors on. Read when want see finished file, not form.

`validate_bids.py` also uses key names in both dirs to catch misspelled sidecar keys — official validator ignores this. Key renamed here changes what checker accepts.

Example's signal: 10 s synthetic noise. Everything else what real conversion should look like.

```
examples/
  dataset_description.json
  participants.tsv
  participants.json
  README
  CHANGES
  sub-01/eeg/
    sub-01_task-gonogo_eeg.edf
    sub-01_task-gonogo_eeg.json
    sub-01_task-gonogo_channels.tsv
    sub-01_task-gonogo_events.tsv
    sub-01_task-gonogo_events.json
```

## What each file is showing you

**`dataset_description.json`** carries provenance Step 3 says ask for: `License`, `Authors`, `Funding`, `EthicsApprovals`, `ReferencesAndLinks`, `DatasetDOI`. `write_bids_metadata.py` writes all these; `--doi` and `--references-and-links` flags people miss.

**`participants.json`** maps each column to **one object**, not array, spells key `Levels` with capital L. Both mistakes common, validator doesn't reliably catch either. Every column here exists in `participants.tsv`, none exists there without entry here.

**`sub-01_task-gonogo_eeg.json`** shows types written wrong: `RecordingDuration` number, not `"10.0"`. `SamplingFrequency` and `PowerLineFrequency` numbers. Misc count is `MiscChannelCount`; `MISCChannelCount` deprecated alias some docs tables still show. `HardwareFilters` object; `SoftwareFilters` is `"n/a"` here since none applied — honest value, not placeholder.

`EEGGround` is `"n/a"` since source docs never stated it. Correct entry. Filling plausible ground location = fabrication skill's second rule warns about.

**`channels.tsv`** has `name`, `type`, `units` first, that order. `type` uppercase, from BIDS vocabulary. `status` marks one bad channel, `status_description` says why. `EOG` type matches `EOGChannelCount: 1` in sidecar; declaring `VEOG` there while sidecar counts `EOG` raises validator warning.

**`events.tsv` and `events.json`** keep both readable `trial_type` and raw `value` amplifier recorded, `events.json` documents both with `Levels`. `response_time` is `"n/a"` on No-Go trials, spelled out, never blank. When trigger codes undocumented, keep `value`, say in `Description` source doesn't explain them — don't invent `Levels`.

**`README`** covers what sidecars can't: study overview, methods
(participants/acquisition/task/paradigm), known data-quality issues,
references, contact. Nine sections, several marked optional — omit a
section that doesn't apply (e.g. `Experimental design` for resting state)
rather than filling it with a placeholder. Full section list in
`templates/README`.

## Which of these files you actually need

`templates/` menu, not checklist. Copying all of it = dataset full of forms nobody filled. Only four files REQUIRED in every EEG dataset:

| File | Level | Needed |
|---|---|---|
| `dataset_description.json` | root | **REQUIRED** |
| `README` | root | **REQUIRED** |
| `sub-<label>/eeg/..._eeg.<ext>` | recording | **REQUIRED** (the data) |
| `sub-<label>/eeg/..._eeg.json` | recording | **REQUIRED** |
| `participants.tsv` + `participants.json` | root | RECOMMENDED, expected in practice |
| `..._channels.tsv` | recording | RECOMMENDED, written by mne-bids |
| `..._events.tsv` + `..._events.json` | recording | only if recording has events |
| `CHANGES` | root | OPTIONAL |
| `LICENSE` | root | OPTIONAL, only if know licence |
| `task-<label>_eeg.json` | root | OPTIONAL, see below |
| `..._electrodes.tsv` + `..._coordsystem.json` | recording | OPTIONAL, wrong unless positions measured |

Absent optional file = statement dataset lacks that info. Present one filled with placeholders/guesses = false statement. First always better.

## The root-level `task-<label>_eeg.json`

Optional, one file mne-bids won't write for you. Sits at dataset root, applies to every recording whose filename carries that `task-<label>`, every subject/session, since names no entity data files lack. That's inheritance principle: keys load top of tree downward, key repeated in recording's own `_eeg.json` overrides for that recording only.

Use for what's identical across dataset: hardware, reference, line frequency, task description. Per-recording sidecars then carry only what genuinely varies. On 100-subject dataset that's diff between one edit and hundred.

`convert_recording.py` writes per-recording sidecars. Want inheritance? Write this file by hand, delete duplicated keys from per-recording ones. Leaving out equally valid; nothing breaks.

## `electrodes.tsv` and `coordsystem.json`

Both files OPTIONAL, writing them wrong unless positions really measured on these participants. Expanding template montage into coordinates = fabricated `electrodes.tsv`, spec violation; absent one fine. `references/electrodes.md` covers decision. Read before filling these in.

If write them, note carry no `task-` entity: electrode positions belong to session, not one task, spec says don't duplicate per data file. If `electrodes.tsv` exists, `coordsystem.json` MUST exist too.

## Files not templated here

`LICENSE` holds full text of licence named in `dataset_description.json`. Optional, only worth adding once someone told you which licence applies.

`_scans.tsv` written by mne-bids. `sessions.tsv`, `_channels.json`, `_physio.tsv.gz`, `_stim.tsv.gz` and `_photo.*` valid BIDS but rare in conversion; see `bids_reference.md` or spec if dataset needs one.