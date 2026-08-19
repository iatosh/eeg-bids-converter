# BIDS Converter for EEG

<!-- BIDS logo — https://bids.neuroimaging.io/ -->
<p align="center">
  <a href="https://bids.neuroimaging.io/">
    <img src="assets/BIDS_Logo.png" alt="Brain Imaging Data Structure (BIDS) — https://bids.neuroimaging.io/" width="220">
  </a>
</p>

## Overview

An agent skill that converts arbitrary raw EEG datasets (EDF, BrainVision,
EEGLAB `.set`, Biosemi BDF, GDF, CNT, Curry `.cdt`, custom MATLAB `.mat`
structs, or anything else MNE can read) into a spec-valid
[BIDS](https://bids.neuroimaging.io/) dataset using `mne` / `mne-bids`.

## Requirements

**[uv](https://docs.astral.sh/uv/)**, and nothing else. Every script in
`scripts/` carries its dependencies inline as
[PEP 723](https://peps.python.org/pep-0723/) metadata, so `uv run` installs
them into a throwaway environment on first use — no virtualenv to create,
nothing left on your system Python.

Or, if you would rather use an existing Python 3.10+:

```bash
pip install "mne>=1.6" "mne-bids>=0.14" "pybv>=0.7.3" \
            pandas openpyxl edfio eeglabio curryreader bids-validator-deno
```

and tell the agent to use `python3` in place of `uv run`.
(`bids-validator-deno` is self-contained: no separate Node or Deno install.)

## Usage

1. Clone this repository: `git clone https://github.com/iatosh/eeg-bids-converter.git`
2. Place the folder into your agent's skills directory.
3. Invoke via `/eeg-bids-converter`, or just point the agent at a folder of raw
   EEG recordings and ask for BIDS.

## How it Works

The skill follows the
[BIDS EEG Specification](https://bids-specification.readthedocs.io/en/stable/modality-specific-files/electroencephalography.html),
producing `sub-<label>/[ses-<label>/]eeg/`. The steps run in order; each one
runs a script or makes one scoped decision.

1. **Survey** — `inspect_dataset.py` lists every extension, which files MNE can
   actually read, and which look like external event or metadata files. Then
   the agent reads the dataset's own README/paper, following a DOI if that is
   all the local docs give.
2. **Map filenames to entities** — a regex with named groups
   (`subject`, `session`, `task`, `run`, `acq`), dry-run through
   `inspect_dataset.py --pattern` until every recording maps to entities that
   read *correctly*, not merely until the regex matches.
3. **Collect what only the docs and the user can answer** — `PowerLineFrequency`,
   `EEGReference`, `EEGGround`, `Manufacturer`, event-code semantics, electrode
   provenance, license and citation. None of it is derivable from the signal.
   Open questions go to the user in one batch, before anything is written.
4. **Convert** — `convert_recording.py`, once per recording, same call shape
   every time. After each write it re-reads the file and compares sampling
   rate, duration and waveform against the source. Formats outside BIDS's four
   accepted ones (EDF, BDF, BrainVision, EEGLAB) are converted to BrainVision.
5. **Patch the sidecars** — `patch_sidecar.py` writes in the Step 3 facts
   `mne-bids` cannot infer, chiefly `EEGReference` and `EEGGround`. It also
   fixes `Manufacturer`, which `mne-bids` fills from the *written* file format:
   a Neuroscan recording converted to BrainVision otherwise claims
   `"Brain Products"`, and no validator flags it.
6. **Dataset metadata, then validate** — `write_bids_metadata.py` writes
   `dataset_description.json`, `participants.tsv` + `participants.json`,
   `README` and `CHANGES`. This runs **last**: `write_raw_bids()` rewrites
   `participants.tsv` on every call. Then `validate_bids.py` runs the official
   BIDS validator, plus a key-spelling check against a hand-verified reference
   dataset (the official validator silently ignores keys it does not
   recognise).
7. **Report** — what was converted, what the validator said, and every judgment
   call with its source: what was inferred, what could not be determined, what
   was deliberately left out.

### Agent Behavior

- **Never modifies the source dataset.** Reads from it, writes elsewhere. If a
  source file needs repairing to be readable, the repair happens on a scratch
  copy.
- **Records what the dataset says, not what would look complete.** A
  plausible-sounding guess is data corruption no validator will catch.
- **Asks before falling back to `"n/a"`.** The order is documentation, then the
  user, then `"n/a"`. Users often know the recording country, the hardware, or
  what a trigger code meant even when the dataset never wrote it down. When no
  user is reachable (batch run, subagent, CI), the ladder is docs then `"n/a"`,
  and the unasked questions are logged in the Step 7 report.
- **Fixes root causes on validation failure.** Errors are never silenced to
  make a run pass.
- **Treats zero validator errors as necessary, not sufficient.** The validator
  checks structure. It cannot see a sidecar naming hardware the recording never
  used, a trigger code named by guess, or samples written in the wrong order.
  What finishes a conversion is the Step 4 read-back check passing for every
  recording and an honest Step 7 record.

### Situational references

`references/` holds documents the agent reads only when it hits their
situation: `custom_formats.md` (MNE cannot open the file), `events.md`
(events not in `raw.annotations`, or trigger codes to document),
`electrodes.md` (electrode positions and `--montage`), `derivatives.md`
(source ships already-filtered copies), `bids_reference.md` (spec facts), and
`templates_and_examples.md` (finished metadata files).

## License

MIT License — see [LICENSE](LICENSE).
The BIDS logo belongs to the BIDS community: <https://bids.neuroimaging.io/>.
