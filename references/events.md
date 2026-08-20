# When events don't come from embedded annotations

Read this when recording's events live somewhere other than annotations
mne already reads: trigger channel, marker array, separate csv/tsv/
txt/mat file. Also when need document trigger codes' meaning.

If `mne.io.read_raw(...).annotations` already holds events, skip this file:
pass `--annotations-only` and mne-bids writes both
`events.tsv` and `events.json` for you.

## Contents
- [The two write paths](#the-two-write-paths)
- [Getting events out of the source](#getting-events-out-of-the-source)
- [Documenting the codes](#documenting-the-codes)
- [events.tsv columns](#eventstsv-columns)

## The two write paths

Target always one of exactly two things:

| you have | flag | who writes events.json |
|---|---|---|
| annotations on Raw | `--annotations-only` | mne-bids, automatically |
| table you built | `--events-csv <path>` | **you**, via `--events-descriptions` |

Never both for one recording. Two writers race over one `events.tsv`.
Neither correct only when recording genuinely has no events.

`--events-csv` path has no automatic `events.json`, so
`--events-descriptions` not optional there: without it every non-obvious
column ships undocumented.

```bash
uv run scripts/convert_recording.py --input <file> --bids-root <root> \
    --subject 01 --task oddball --line-freq 50 \
    --events-csv /tmp/sub01_events.csv \
    --events-descriptions '{"trial_type": {"Description": "Stimulus category",
        "Levels": {"standard": "Frequent tone", "target": "Rare tone"}}}'
```

File read with `pandas.read_csv` defaults, so write it **comma**-
separated even though BIDS itself TSV everywhere. Columns:
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
pass to `--events-csv`. Don't hand-write `events.tsv` directly. That's
how you get two writers disagreeing.

Check units source used. Onsets recorded in milliseconds or samples
both look plausible as seconds, neither script nor validator notice;
1000x error in onset silently misaligns every epoch.

## Documenting the codes

Look up what numbers mean in dataset's own docs before building
`code_to_label`. Emitting `event_251`/`event_252` when README says
"251 = deviant onset, 252 = standard onset" discards info that was
right there.

If codes really undocumented, keep raw number in `value`
column and say so. Don't name them by guess.

```bash
--events-descriptions '{"value": {"Description":
    "Raw trigger code as recorded. The source dataset does not document
     what these codes mean."}}'
```

That's honest sidecar. Invented `Levels` mapping isn't, and no
validator ever flags it.

## events.tsv columns

REQUIRED: `onset` (seconds from acquisition start, negative allowed),
`duration` (seconds, >= 0; `0` = instantaneous event).

Common/recommended: `trial_type` (categorical label, use rather than
`description`), `response_time`, `stim_file`, `value`, `sample`, `HED`,
`channel`.

Rules: sort by ascending `onset`; missing values are literal string
`"n/a"`, never blank. Document non-obvious columns, especially categorical
`trial_type`/`value` codes, in accompanying `_events.json` via
`Levels`.

`task-<label>_events.json` may live at dataset root and be inherited by
every run of that task via Inheritance Principle. `TaskName` REQUIRED
there whenever `task-` entity used.