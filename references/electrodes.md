# When electrodes positions involved

Read when dataset say anything about where electrodes were, or tempted to pass `--montage`.

Decision one question: **positions actually measured on these participants' heads?**

| what you have | what to write |
|---|---|
| digitized 3D coordinates from source | `electrodes.tsv` + `coordsystem.json` |
| only name of layout ("10-20", "Quik-Cap 128") | `EEGPlacementScheme` in `eeg.json`, and **no** electrodes.tsv |
| nothing | neither |

Template montage expanded into coordinates = fabricated `electrodes.tsv`: claims measured provenance for numbers nobody measured. Spec violation. Absent `electrodes.tsv` not.

## Contents
- [Only the scheme name](#only-the-scheme-name)
- [Real digitized positions](#real-digitized-positions)
- [Positions without fiducials](#positions-without-fiducials)
- [File requirements](#file-requirements)

## Only the scheme name

Skip `--montage`. Record scheme as string instead:

```bash
uv run scripts/patch_sidecar.py --bids-root <root> \
    --entries '{"EEGPlacementScheme": "10-20"}'
```

`--montage standard_1020` correct only when recording genuinely used that layout AND you intend resulting coordinates read as real. Rare in practice; flag exists for datasets whose own docs say standard positions applied.

## Real digitized positions

Positions source actually measured worth keeping, routinely dropped by accident. Dataset whose README advertise "the locations of 3D EEG electrodes" easy to convert without ever extracting them.

Attach to Raw **before** writing; `write_raw_bids` emits `electrodes.tsv` and `coordsystem.json` from montage at write time. Doing as later read-modify-write pass over already-written recording deletes data file out from under lazily-loaded Raw.

```python
# coords: {channel_name: (x, y, z)} in METRES, head coordinate frame
montage = mne.channels.make_dig_montage(
    ch_pos=coords,
    nasion=nas, lpa=lpa, rpa=rpa,     # see below, these matter
    coord_frame="head")
raw.set_montage(montage, on_missing="warn")
raw.save("/tmp/sub01_raw.fif", overwrite=True)
```

Coordinates in `.mat` usually `(n_channels, 3)` array plus separate channel-name list; check units (millimetres common, MNE wants metres), confirm name order match `raw.ch_names` rather than assume. See `references/custom_formats.md` for reading `.mat`.

## Positions without fiducials

Head-frame montage with no nasion / left / right pre-auricular landmarks cannot be written: mne-bids raises

```
'head' coordinate frame must contain nasion and left and right
pre-auricular point landmarks
```

refuses **whole recording**, not just positions. EEGLAB `chanlocs` frequently land here.

`convert_recording.py` handles by dropping positions and writing recording, with printed notice. Right trade: inventing landmarks to satisfy writer would produce exactly fabricated `electrodes.tsv` this file exists to prevent. Set `EEGPlacementScheme` instead, say so in Step 7 report.

If source really does provide fiducials elsewhere in its files, supplying them better than losing coordinates. Look before accepting drop.

## File requirements

If `electrodes.tsv` written, `coordsystem.json` MUST also be written.

`electrodes.tsv` REQUIRED columns: `name`, `x`, `y`, `z`.
Recommended: `type`, `material`, `impedance`.

`coordsystem.json` REQUIRED: `EEGCoordinateSystem`, `EEGCoordinateUnits`.
Recommended: `EEGCoordinateSystemDescription`, `FiducialsDescription`,
`FiducialsCoordinates`.

`acq-<label>` entity exists for case where positions recorded with different device than signal.