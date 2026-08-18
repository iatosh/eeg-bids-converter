# When mne cannot read the source

**Read this only after `mne.io.read_raw` has actually failed on the file.**
`convert_recording.py` delegates reading to mne, which ships 30 readers and
covers far more than the obvious four -- Curry `.cdt`, EGI `.mff`, Persyst
`.lay`, Nihon Kohden `.EEG`, ANT `.cnt` and others all read natively. Assuming
a format is unsupported because it looks proprietary is how datasets end up
hand-parsed for no reason.

That mistake is expensive. A hand-written parser that guesses the sample
layout wrong yields a file with the right channel names, the right sample
count, the right sampling rate, and a waveform that correlates with the real
signal at r = 0.000 -- and the BIDS validator reports zero errors. This is not
hypothetical; it happened to a 133-channel Curry recording that
`mne.io.read_raw_curry` reads in one line.

So: try `mne.io.read_raw(path)` first. If it raises about a missing package
(`curryreader`, `defusedxml`, `eeglabio`), add the package, don't write a
parser.

## Contents
- [The universal bridge](#the-universal-bridge)
- [Checking that you parsed it correctly](#checking-that-you-parsed-it-correctly)
- [Exploring an unknown .mat file](#exploring-an-unknown-mat-file)
- [Loading .mat into a Raw](#loading-mat-into-a-raw)
- [One source file, several recordings](#one-source-file-several-recordings)

## The universal bridge

Don't write a second conversion path. Build an `mne.io.RawArray`, save it as
`.fif`, and feed that to the same script every other format goes through:

```python
import mne

info = mne.create_info(ch_names, sfreq=sfreq, ch_types=ch_types)  # "eeg"/"eog"/"ecg"/"misc"
raw = mne.io.RawArray(data, info, verbose=False)                  # data: (n_channels, n_samples), VOLTS
# raw.set_annotations(...)   # if you have events -- see references/events.md
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

**Shape.** `RawArray` wants `(n_channels, n_samples)`. Sources disagree:
scipy `.mat` files are often `(n_samples, n_channels)` and need `.T`, HDF5
v7.3 files come back transposed relative to scipy, and raw binary blobs may
be sample-interleaved rather than channel-blocked. Guessing wrong here is
exactly the failure described at the top of this file.

## Checking that you parsed it correctly

`convert_recording.py` verifies the file it writes against the Raw you hand
it, so a bad parse survives that check -- both sides are equally wrong.
Verify the `RawArray` itself, before writing anything. Two cheap statistics
separate a good parse from a scrambled one:

```python
import numpy as np
X = raw.get_data(picks=range(8), stop=50000)

# 1. Lag-1 autocorrelation. Real EEG is >= ~0.9 at any usual sampling rate:
#    consecutive samples are nearly the same voltage. If the channel/sample
#    axes are swapped, consecutive samples come from different electrodes and
#    this collapses toward zero.
lag1 = [np.corrcoef(x[:-1], x[1:])[0, 1] for x in X]

# 2. Spread of per-channel standard deviation. Real electrodes differ a lot
#    from each other. A scrambled read mixes every channel into every channel,
#    which makes them all look identical.
s = X.std(axis=1); cv = s.std() / s.mean()

# 3. Voltage range. After conversion to volts, EEG lives around 1e-5..1e-4 V.
#    Off by 10^6 means the microvolt scaling is wrong.
print(np.abs(X).max())
```

Measured on the Curry file mentioned above, correct parse vs transposed parse:

| statistic | correct | scrambled |
|---|---|---|
| mean lag-1 autocorrelation | **+0.9967** | **-0.2272** |
| per-channel std, coeff. of variation | **3.665** | **0.031** |

Lag-1 is the sharper of the two: a uniform variance spread can also come from
genuinely stationary noise, but autocorrelation only collapses when the time
axis itself is wrong. If either looks like the right-hand column, re-read the
file's own header for its sample layout instead of adjusting the numbers.

Where a reference reader exists at all -- even a slow or partial one -- read
the same file both ways and correlate. That is the only check that catches a
parse which is self-consistently wrong.

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

If the `.mat` also carries digitized electrode coordinates, see
`references/electrodes.md` -- real positions are worth keeping and are
routinely dropped by accident.

## One source file, several recordings

A `.mat` often holds several separate recordings in one file: one field per
task, or a cell array of runs. `inspect_dataset.py --out` maps one path to
one set of entities and cannot express this, so the split happens in your
loader, not in the regex.

Build one `RawArray` per recording, save one `.fif` each, and call
`convert_recording.py` once per file with the entity that actually
distinguishes them:

```python
for task, field in {"rest": "rest", "imageryleft": "imagery_left",
                    "imageryright": "imagery_right"}.items():
    data = mat[field].astype(float) * 1e-6
    raw = mne.io.RawArray(data, info, verbose=False)
    raw.save(f"/tmp/sub01_{task}_raw.fif", overwrite=True)
```

Choose the entity deliberately, and say which you chose in the Step 7 report:

- **different task** -> `--task` (different paradigm: rest vs motor imagery)
- **same task repeated** -> `--run` (run indices are for repetitions of one task)
- **same task, different acquisition setup** -> `--acq`

Left-hand and right-hand motor imagery are the awkward case: they are two
conditions of one paradigm, so `--task imagery` with the side recorded as an
event/`trial_type` is usually truer than inventing two tasks. If the source
stores them as separate continuous recordings with no shared timeline, two
tasks or two runs are both defensible -- pick one, and record why.
