# When mne cannot read the source

**Read only after `mne.io.read_raw` actually failed on file.**
`convert_recording.py` delegates reading to mne, ships 30 readers, covers far more than obvious four: Curry `.cdt`, EGI `.mff`, Persyst `.lay`, Nihon Kohden `.EEG`, ANT `.cnt` and others read natively. Assuming format unsupported cuz looks proprietary — that how datasets end up hand-parsed for no reason.

Mistake expensive. Hand-written parser guessing sample layout wrong yields file with right channel names, right sample count, right sampling rate, and waveform correlating with real signal at r = 0.000 — BIDS validator reports zero errors. Not hypothetical; happened to 133-channel Curry recording that `mne.io.read_raw_curry` reads in one line.

So: try `mne.io.read_raw(path)` first. If raises about missing package (`curryreader`, `defusedxml`, `eeglabio`), add package, don't write parser.

## Contents
- [The universal bridge](#the-universal-bridge)
- [Checking that you parsed it correctly](#checking-that-you-parsed-it-correctly)
- [Exploring an unknown .mat file](#exploring-an-unknown-mat-file)
- [Loading .mat into a Raw](#loading-mat-into-a-raw)
- [One source file, several recordings](#one-source-file-several-recordings)

## The universal bridge

Don't write second conversion path. Build `mne.io.RawArray`, save as `.fif`, feed to same script every other format goes through:

```python
import mne, numpy as np

info = mne.create_info(ch_names, sfreq=sfreq, ch_types=ch_types)  # "eeg"/"eog"/"ecg"/"misc"
raw = mne.io.RawArray(data, info, verbose=False)                  # data: (n_channels, n_samples), VOLTS

# Do not skip this. A wrong sample layout produces a Raw with the right
# channel names, the right sample count and the right sampling rate, whose
# waveform correlates with the real signal at r = 0.000. Nothing downstream
# catches it: convert_recording.py compares its output against this Raw, so a
# bad parse survives that check, and the validator never looks at samples.
X = raw.get_data(picks=range(min(8, len(ch_names))), stop=50000)
lag1 = np.mean([np.corrcoef(x[:-1], x[1:])[0, 1] for x in X])
sd = X.std(axis=1)
assert lag1 > 0.9, f"lag-1 autocorrelation {lag1:.3f}: sample order is scrambled"
assert sd.std() / sd.mean() > 0.1, "every channel has the same variance: channels are mixed"
assert 1e-6 < np.abs(X).max() < 1e-2, f"peak {np.abs(X).max():.2e} V: unit scaling is wrong"

# raw.set_annotations(...)   # if you have events, see references/events.md
raw.save("/tmp/sub01_raw.fif", overwrite=True)
```

Three assertions explained in [Checking that you parsed it correctly](#checking-that-you-parsed-it-correctly), numbers measured on real corruption. Read that section if one fires.
```bash
uv run scripts/convert_recording.py --input /tmp/sub01_raw.fif --format fif \
    --bids-root /out/bids --subject 01 --task rest --line-freq 50 --annotations-only
```
Delete temp `.fif` after; scratch, not output.

**Units.** MNE/BIDS expect volts. Most `.mat` exports store microvolts, need `* 1e-6` — but verify per dataset, don't apply reflexively. Some store volts already, some record unit in separate metadata column. Get this wrong, scales every downstream analysis by 10^6, nothing in pipeline catches it.

**Shape.** `RawArray` wants `(n_channels, n_samples)`. Sources disagree: scipy `.mat` files often `(n_samples, n_channels)`, need `.T`; HDF5 v7.3 files come back transposed relative to scipy; raw binary blobs may be sample-interleaved rather than channel-blocked. Guess wrong here, exactly the failure described at top of file.

## Checking that you parsed it correctly

`convert_recording.py` verifies file it writes against Raw you hand it — bad parse survives that check. Both sides equally wrong. Verify `RawArray` itself, before writing anything. Two cheap statistics separate good parse from scrambled one:

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

Measured on Curry file mentioned above, correct parse vs transposed parse:

| statistic | correct | scrambled |
|---|---|---|
| mean lag-1 autocorrelation | **+0.9967** | **-0.2272** |
| per-channel std, coeff. of variation | **3.665** | **0.031** |

Lag-1 sharper of two: uniform variance spread can also come from genuinely stationary noise, but autocorrelation only collapses when time axis itself wrong. If either looks like right-hand column, re-read file's own header for sample layout instead of adjusting numbers.

Where reference reader exists at all, even slow or partial one, read same file both ways and correlate. Only check that catches parse self-consistently wrong.

## Exploring an unknown .mat file

Look before writing loader. Field names differ every dataset.

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

v7.3 / HDF5. Note arrays come back transposed relative to scipy:
```python
import h5py
with h5py.File(path, "r") as f:
    data = f["EEG/data"][:].astype(float).T * 1e-6
    sfreq = float(f["EEG/srate"][()].flatten()[0])
```
Cell arrays (e.g. channel-name lists) are arrays of HDF5 object references; dereference each with `f[ref]` before decoding.

If `.mat` also carries digitized electrode coordinates, see `references/electrodes.md`. Real positions worth keeping, routinely dropped by accident.

## One source file, several recordings

`.mat` often holds several separate recordings in one file: one field per task, or cell array of runs. `inspect_dataset.py --out` maps one path to one set of entities, cannot express this — split happens in your loader, not in the regex.

Build one `RawArray` per recording, save one `.fif` each, call `convert_recording.py` once per file with entity that actually distinguishes them:

```python
for task, field in {"rest": "rest", "imageryleft": "imagery_left",
                    "imageryright": "imagery_right"}.items():
    data = mat[field].astype(float) * 1e-6
    raw = mne.io.RawArray(data, info, verbose=False)
    raw.save(f"/tmp/sub01_{task}_raw.fif", overwrite=True)
```

Choose entity deliberately, say which chosen in Step 7 report:

- **different task** -> `--task` (different paradigm: rest vs motor imagery)
- **same task repeated** -> `--run` (run indices are for repetitions of one task)
- **same task, different acquisition setup** -> `--acq`

Left-hand and right-hand motor imagery awkward case: two conditions of one paradigm, so `--task imagery` with side recorded as event/`trial_type` usually truer than inventing two tasks. If source stores them as separate continuous recordings with no shared timeline, two tasks or two runs both defensible. Pick one, record why.