# Worked example (`references/examples/`)

A complete, spec-valid, one-subject EEG dataset. Copy a file from here when you
need to see the shape of a finished one. `validate_bids.py` reports 0 errors on
this directory.

The signal is 10 s of synthetic noise. Everything else is what a real
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
`PowerLineFrequency` are numbers. `MISCChannelCount` is all caps, unlike every
other `*ChannelCount`. `HardwareFilters` is an object; `SoftwareFilters` is
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
