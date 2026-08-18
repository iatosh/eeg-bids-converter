# Templates and worked example


Two directories, same layout, different jobs.

**`templates/`** is what you copy. Every value is a placeholder stating the
requirement level, the type, and what the field is for:

```json
"PowerLineFrequency": "<REQUIRED | number | 50 or 60, follows the recording country>",
"RecordingDuration": "<RECOMMENDED | number | seconds. A number, not a quoted string>",
```

The directory names carry the layout too: `sub-<label>/eeg/`,
`sub-<label>_task-<label>_eeg.json`. Copy the tree, rename the entities,
replace the placeholders.

**`examples/`** is what a filled-in result looks like. It is a real one-subject
dataset that `validate_bids.py` reports 0 errors on. Read it when you want to
see a finished file rather than a form.

`validate_bids.py` also uses the key names in both directories to catch
misspelled sidecar keys, which the official validator ignores. So a key
renamed here changes what the checker accepts.

The example's signal is 10 s of synthetic noise. Everything else is what a real
conversion should look like.

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

**`dataset_description.json`** carries the provenance Step 3 tells you to ask
for: `License`, `Authors`, `Funding`, `EthicsApprovals`, `ReferencesAndLinks`,
`DatasetDOI`. `write_bids_metadata.py` writes all of these; `--doi` and
`--references-and-links` are the flags people miss.

**`participants.json`** maps each column to **one object**, not to an array,
and spells the key `Levels` with a capital L. Both mistakes are common and the
validator does not reliably catch either. Every column here exists in
`participants.tsv`, and no column exists there without an entry here.

**`sub-01_task-gonogo_eeg.json`** shows the types that get written wrong:
`RecordingDuration` is a number, not `"10.0"`. `SamplingFrequency` and
`PowerLineFrequency` are numbers. The misc count is `MiscChannelCount`;
`MISCChannelCount` is a deprecated alias that some documentation tables still
show. `HardwareFilters` is an object; `SoftwareFilters` is
`"n/a"` here because none were applied, which is the honest value, not a
placeholder.

`EEGGround` is `"n/a"` because the source documentation never stated it. That
is the correct entry. Filling in a plausible ground location would be the
fabrication the skill's second rule is about.

**`channels.tsv`** has `name`, `type`, `units` first and in that order. `type`
is uppercase and from the BIDS vocabulary. `status` marks the one bad channel,
with `status_description` saying why. The `EOG` type matches
`EOGChannelCount: 1` in the sidecar; declaring `VEOG` there while the sidecar
counts an `EOG` raises a validator warning.

**`events.tsv` and `events.json`** keep both a readable `trial_type` and the
raw `value` the amplifier recorded, and `events.json` documents both with
`Levels`. `response_time` is `"n/a"` on No-Go trials, spelled out, never left
blank. When trigger codes are undocumented, keep `value` and say in
`Description` that the source does not explain them, rather than inventing
`Levels`.

**`README`** covers what the sidecars cannot: what was recorded, the paradigm,
known data-quality issues, the source URL, and what was inferred rather than
read.
