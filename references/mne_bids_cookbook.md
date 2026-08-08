# mne-bids cookbook

Code patterns for what `scripts/convert_recording.py` can't do on its own:
sources with no native MNE reader, and turning odd event representations
into something the scripts accept. Read this only when a dataset needs
custom Python.

## Contents
- [The universal bridge (custom formats)](#the-universal-bridge)
- [Exploring an unknown .mat file](#exploring-an-unknown-mat-file)
- [Loading .mat into a Raw](#loading-mat-into-a-raw)
- [Building events from whatever the source provides](#building-events-from-whatever-the-source-provides)
- [Per-format gotchas](#per-format-gotchas)

## The universal bridge

`convert_recording.py` reads edf, bdf, vhdr, set, cnt, gdf, fif natively.
For anything else, don't write a second conversion path -- build an
`mne.io.RawArray`, save it as `.fif`, and feed that to the same script:

```python
import mne

info = mne.create_info(ch_names, sfreq=sfreq, ch_types=ch_types)  # "eeg"/"eog"/"ecg"/"misc"
raw = mne.io.RawArray(data, info, verbose=False)                  # data: (n_channels, n_samples), VOLTS
# raw.set_annotations(...)   # if you have events -- see below
raw.save("/tmp/sub01_raw.fif", overwrite=True)
```
```bash
uv run scripts/convert_recording.py --input /tmp/sub01_raw.fif --format fif \
    --bids-root /out/bids --subject 01 --task rest --line-freq 50 --annotations-only
```
Delete the temp `.fif` afterward; it's scratch, not output.

**Units.** MNE/BIDS expect volts. Most `.mat` exports store microvolts and
need `* 1e-6` -- but verify per dataset rather than applying it reflexively;
some store volts already, and some record the unit in a separate metadata
column. Getting this wrong scales every downstream analysis by 10^6 and
nothing in the pipeline will catch it.

## Exploring an unknown .mat file

Look before writing a loader -- field names differ in every dataset:

```python
# /// script
# dependencies = ["scipy", "h5py", "numpy"]
# ///
import sys, numpy as np

path = sys.argv[1]
is_hdf5 = open(path, "rb").read(8) == b"\x89HDF\r\n\x1a\n"   # MATLAB v7.3 is HDF5

if is_hdf5:
    import h5py
    with h5py.File(path, "r") as f:
        f.visit(print)                    # all dataset paths
        # MATLAB char arrays are uint16 codepoints:
        # "".join(chr(c) for c in f["EEG/setname"][:].flatten())
else:
    from scipy.io import loadmat
    mat = loadmat(path, squeeze_me=True, struct_as_record=False)
    for k, v in mat.items():
        if not k.startswith("__"):
            print(k, getattr(v, "_fieldnames", type(v)), getattr(v, "shape", ""))
```

## Loading .mat into a Raw

Classic (pre-v7.3):
```python
from scipy.io import loadmat
eeg = loadmat(path, squeeze_me=True, struct_as_record=False)["EEG"]  # struct name varies
data = eeg.data.astype(float) * 1e-6        # verify the scale factor
sfreq = float(eeg.srate)
```

v7.3 / HDF5 -- note arrays come back transposed relative to scipy:
```python
import h5py
with h5py.File(path, "r") as f:
    data = f["EEG/data"][:].astype(float).T * 1e-6
    sfreq = float(f["EEG/srate"][()].flatten()[0])
```
Cell arrays (e.g. channel-name lists) are arrays of HDF5 object references;
dereference each with `f[ref]` before decoding.

## Building events from whatever the source provides

The target is always one of two things: annotations on the Raw (then
`--annotations-only`), or a CSV with `onset,duration,trial_type[,value]`
in seconds (then `--events-csv`). Never both for one recording.

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

**Numeric codes:** look up what they mean in the dataset's own docs before
building `code_to_label`. Emitting `event_251`/`event_252` when the README
says "251 = deviant onset, 252 = standard onset" discards information that
was right there. If the codes really are undocumented, keep the raw number
in a `value` column and say so in `--events-descriptions`.

**External event file** (csv/tsv/txt/lab/tse_agg): parse it, compute onset
and duration in seconds, write `onset,duration,trial_type[,value]`, pass it
to `--events-csv`. Don't hand-write events.tsv -- that's how you get two
writers disagreeing.

## Per-format gotchas

**BrainVision** is a triplet (`.vhdr` + `.eeg` + `.vmrk`) where the `.vhdr`
names its siblings internally. Reorganizing an archive renames files but
not those pointers, and mne then fails with a confusing "file not found".
`convert_recording.py` detects this and says so. Fix it by copying the
triplet to scratch and correcting the pointers *there* -- never edit files
in the source dataset.

**EDF** truncates channel names at 16 characters and stores 16-bit samples
against a fixed physical range. For long channel names or wide dynamic
range, write BrainVision instead (`--output-format BrainVision`).

**BDF** is a valid BIDS format but *not* a valid explicit `format=` target
for mne-bids. Any channel edit forces a preload, which forces an explicit
format, so BDF sources come out as BrainVision. That's expected, not a bug.

**GDF/CNT** aren't BIDS formats at all; they always get converted on write.
If mne's reader produces garbled channels, converting via EEGLAB first is a
reasonable fallback.

**Anonymization.** For real recording dates, pass `--anonymize-daysback N`
consistently across every recording in the dataset. Applying it to some
recordings and not others is worse than not doing it at all -- it implies a
guarantee the dataset doesn't actually have.
