# When the source ships preprocessed copies

Read this when the dataset contains an already-filtered, re-referenced, ICA-
cleaned or otherwise processed version of the recordings alongside the raw
ones.

Such a copy must not go into the raw `sub-*/` tree -- BIDS raw means
minimally processed. It also must not be silently dropped. Either it goes
into a derivatives dataset, or you leave it out and say so in the Step 7
report. Dropping it without mention is the one option that isn't acceptable.

Deciding which is a Step 3 question for the user: keeping a derivatives tree
roughly doubles the conversion work, and for some datasets the processed
copy is the only part anyone uses.

## Writing it

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

`--desc` is only ever for a derivatives tree. Setting it on a raw recording
labels a file as processed when it isn't.

Record the actual filter settings in `SoftwareFilters` with
`patch_sidecar.py`, using the source's own numbers. If the source states
exactly what was done, `"n/a"` there is a loss, not honesty.

## Validate it

```bash
uv run scripts/validate_bids.py <bids_root> --recursive
```

**The validator skips `derivatives/` content by default.** Without
`--recursive` it passes without ever having checked the derivatives tree.

## Spec requirements

- Directory template:
  `derivatives/<pipeline-name>/sub-<label>/[ses-<label>/]eeg/<source-entities>[_desc-<label>]_<suffix>.<extension>`
  -- same entities as the raw file it derives from, plus `desc-<label>`
  (RECOMMENDED) to distinguish it from the raw version.
- A `dataset_description.json` **MUST** exist at the top of the derivatives
  folder -- `derivatives/<pipeline-name>/dataset_description.json`, not the
  raw dataset's.
- Unlike raw datasets (where `GeneratedBy` is RECOMMENDED), a derivatives
  `dataset_description.json` **MUST include `GeneratedBy`**, with `Name`
  REQUIRED and `Version`/`Description`/`CodeURL`/`Container`
  RECOMMENDED/OPTIONAL.
- If the derivatives folder is nested inside the raw dataset
  (`<raw_root>/derivatives/<pipeline-name>/`, the normal case), the first
  `GeneratedBy` object's `Name` MUST be a substring of `<pipeline-name>`.
- `DatasetType` should be `"derivative"`.
- A derivatives sub-dataset does not need its own `participants.tsv` /
  `README` -- it inherits those from the parent raw dataset.
  `write_bids_metadata.py --dataset-type derivative` skips writing them and
  removes the placeholders `write_raw_bids()` auto-bootstraps there.
