# When electrode positions are involved

Read this when the dataset says anything about where the electrodes were,
or when you are tempted to pass `--montage`.

The decision is one question: **do you have positions that were actually
measured on these participants' heads?**

| what you have | what to write |
|---|---|
| digitized 3D coordinates from the source | `electrodes.tsv` + `coordsystem.json` |
| only the name of a layout ("10-20", "Quik-Cap 128") | `EEGPlacementScheme` in `eeg.json`, and **no** electrodes.tsv |
| nothing | neither |

A template montage expanded into coordinates is a fabricated
`electrodes.tsv`: it claims measured provenance for numbers nobody measured.
That is a spec violation. An absent `electrodes.tsv` is not.

## Contents
- [Only the scheme name](#only-the-scheme-name)
- [Real digitized positions](#real-digitized-positions)
- [Positions without fiducials](#positions-without-fiducials)
- [File requirements](#file-requirements)

## Only the scheme name

Skip `--montage`. Record the scheme as a string instead:

```bash
uv run scripts/patch_sidecar.py --bids-root <root> \
    --entries '{"EEGPlacementScheme": "10-20"}'
```

`--montage standard_1020` is correct only when the recording genuinely used
that layout AND you intend the resulting coordinates to be read as real. In
practice that is rare; the flag exists for datasets whose own documentation
says the standard positions were applied.

## Real digitized positions

Positions the source actually measured are worth keeping, and they are
routinely dropped by accident -- a dataset whose README advertises "the
locations of 3D EEG electrodes" is easy to convert without ever extracting
them.

Attach them to the Raw **before** writing; `write_raw_bids` emits
`electrodes.tsv` and `coordsystem.json` from the montage at write time.
Doing it as a later read-modify-write pass over an already-written recording
deletes the data file out from under a lazily-loaded Raw.

```python
# coords: {channel_name: (x, y, z)} in METRES, head coordinate frame
montage = mne.channels.make_dig_montage(
    ch_pos=coords,
    nasion=nas, lpa=lpa, rpa=rpa,     # see below -- these matter
    coord_frame="head")
raw.set_montage(montage, on_missing="warn")
raw.save("/tmp/sub01_raw.fif", overwrite=True)
```

Coordinates in a `.mat` are usually a `(n_channels, 3)` array plus a
separate channel-name list; check the units (millimetres are common, MNE
wants metres) and confirm the name order matches `raw.ch_names` rather than
assuming it. See `references/custom_formats.md` for reading the `.mat`.

## Positions without fiducials

A head-frame montage with no nasion / left / right pre-auricular landmarks
cannot be written: mne-bids raises

```
'head' coordinate frame must contain nasion and left and right
pre-auricular point landmarks
```

and refuses the **whole recording**, not just the positions. EEGLAB
`chanlocs` frequently land in this state.

`convert_recording.py` handles this by dropping the positions and writing
the recording, with a printed notice. That is the right trade: inventing
landmarks to satisfy the writer would produce exactly the fabricated
`electrodes.tsv` this file exists to prevent. Set `EEGPlacementScheme`
instead and say so in the Step 7 report.

If the source really does provide fiducials somewhere else in its files,
supplying them is better than losing the coordinates -- look before
accepting the drop.

## File requirements

If `electrodes.tsv` is written, `coordsystem.json` MUST also be written.

`electrodes.tsv` REQUIRED columns: `name`, `x`, `y`, `z`.
Recommended: `type`, `material`, `impedance`.

`coordsystem.json` REQUIRED: `EEGCoordinateSystem`, `EEGCoordinateUnits`.
Recommended: `EEGCoordinateSystemDescription`, `FiducialsDescription`,
`FiducialsCoordinates`.

The `acq-<label>` entity exists for the case where positions were recorded
with a different device than the signal.
