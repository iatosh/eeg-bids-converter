# When events don't come from embedded annotations

Read this when the recording's events live somewhere other than annotations
mne already reads: a trigger channel, a marker array, a separate csv/tsv/
txt/mat file. Also when you need to document what the trigger codes mean.

If `mne.io.read_raw(...).annotations` already holds the events, you don't
need this file: pass `--annotations-only` and mne-bids writes both
`events.tsv` and `events.json` for you.

## Contents
- [The two write paths](#the-two-write-paths)
- [Getting events out of the source](#getting-events-out-of-the-source)
- [Documenting the codes](#documenting-the-codes)
- [events.tsv columns](#eventstsv-columns)

## The two write paths

The target is always one of exactly two things:

| you have | flag | who writes events.json |
|---|---|---|
| annotations on the Raw | `--annotations-only` | mne-bids, automatically |
| a table you built | `--events-csv <path>` | **you**, via `--events-descriptions` |

Never both for one recording. Two writers race over one `events.tsv`.
Neither is correct only when the recording genuinely has no events.

The `--events-csv` path has no automatic `events.json`, so
`--events-descriptions` is not optional there: without it every non-obvious
column ships undocumented.

```bash
uv run scripts/convert_recording.py --input <file> --bids-root <root> \
    --subject 01 --task oddball --line-freq 50 \
    --events-csv /tmp/sub01_events.csv \
    --events-descriptions '{"trial_type": {"Description": "Stimulus category",
        "Levels": {"standard": "Frequent tone", "target": "Rare tone"}}}'
```

The file is read with `pandas.read_csv` defaults, so write it **comma**-
separated even though BIDS itself is TSV everywhere. Columns:
`onset,duration,trial_type[,value]`, onset and duration in **seconds**.

## Getting events out of the source

**Embedded trigger channel:**
```python
events = mne.find_events(raw, stim_channel="Status")   # or "TRIGGER"; check raw.ch_names
```

**Marker array** (nonzero sample = event):
```python
idx = np.where(marker != 0)[0]
raw.set_annotations(mne.Annotations(
    onset=idx / sfreq, duration=0.0,
    description=[code_to_label[c] for c in marker[idx]]))
```

**External event file** (csv/tsv/txt/lab/tse_agg/mat): parse it, compute
onset and duration in seconds, write `onset,duration,trial_type[,value]`,
pass it to `--events-csv`. Do not hand-write `events.tsv` directly. That is
how you get two writers disagreeing.

Check the units the source used. Onsets recorded in milliseconds or in
samples both look plausible as seconds and neither the script nor the
validator will notice; a 1000x error in onset silently misaligns every epoch.

## Documenting the codes

Look up what the numbers mean in the dataset's own docs before building
`code_to_label`. Emitting `event_251`/`event_252` when the README says
"251 = deviant onset, 252 = standard onset" discards information that was
right there.

If the codes really are undocumented, keep the raw number in a `value`
column and say so. Do not name them by guess.

```bash
--events-descriptions '{"value": {"Description":
    "Raw trigger code as recorded. The source dataset does not document
     what these codes mean."}}'
```

That is an honest sidecar. An invented `Levels` mapping is not, and no
validator will ever flag it.

## events.tsv columns

REQUIRED: `onset` (seconds from acquisition start, negative allowed),
`duration` (seconds, >= 0; `0` = instantaneous event).

Common/recommended: `trial_type` (categorical label, use this rather than
`description`), `response_time`, `stim_file`, `value`, `sample`, `HED`,
`channel`.

Rules: sort by ascending `onset`; missing values are the literal string
`"n/a"`, never blank. Document non-obvious columns, especially categorical
`trial_type`/`value` codes, in the accompanying `_events.json` via
`Levels`.

`task-<label>_events.json` may live at the dataset root and be inherited by
every run of that task via the Inheritance Principle. `TaskName` is REQUIRED
there whenever a `task-` entity is used.
