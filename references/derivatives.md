# When source ships preprocessed copies

Read when dataset contain already-filtered, re-referenced, ICA-cleaned, or otherwise processed version of recordings alongside raw ones.

Such copy must not go into raw `sub-*/` tree. BIDS raw means minimally processed. Also must not silently drop. Either goes into derivatives dataset, or leave out and say so in Step 7 report. Dropping without mention = only unacceptable option.

Deciding which is Step 3 question for user: keeping derivatives tree roughly doubles conversion work, and for some datasets processed copy only part anyone uses.

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

`--desc` only ever for derivatives tree. Setting on raw recording labels file as processed when it isn't.

Record actual filter settings in `SoftwareFilters` with `patch_sidecar.py`, using source's own numbers. If source states exactly what was done, `"n/a"` there = loss, not honesty.

## Validate it

```bash
uv run scripts/validate_bids.py <bids_root> --recursive
```

**Validator skips `derivatives/` content by default.** Without `--recursive` it passes without ever checking derivatives tree.

## Spec requirements

- Directory template:
  `derivatives/<pipeline-name>/sub-<label>/[ses-<label>/]eeg/<source-entities>[_desc-<label>]_<suffix>.<extension>`
  Same entities as raw file it derives from, plus `desc-<label>`
  (RECOMMENDED) to distinguish from raw version.
- `dataset_description.json` **MUST** exist at top of derivatives
  folder: `derivatives/<pipeline-name>/dataset_description.json`, not
  raw dataset's.
- Unlike raw datasets (where `GeneratedBy` RECOMMENDED), derivatives
  `dataset_description.json` **MUST include `GeneratedBy`**, with `Name`
  REQUIRED and `Version`/`Description`/`CodeURL`/`Container`
  RECOMMENDED/OPTIONAL.
- If derivatives folder nested inside raw dataset
  (`<raw_root>/derivatives/<pipeline-name>/`, normal case), first
  `GeneratedBy` object's `Name` MUST be substring of `<pipeline-name>`.
- `DatasetType` should be `"derivative"`.
- Derivatives sub-dataset doesn't need own `participants.tsv` /
  `README`. Inherits from parent raw dataset.
  `write_bids_metadata.py --dataset-type derivative` skips writing them and
  removes placeholders `write_raw_bids()` auto-bootstraps there.