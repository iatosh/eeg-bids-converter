"""Shared helpers for the eeg-bids-converter skill scripts.

Not a standalone entry point -- imported by the other scripts/*.py files.
Pure stdlib only, so it never needs its own PEP 723 dependency block; it
just has to sit next to the scripts that import it (uv puts the script's
own directory on sys.path[0], so `import _common` works regardless of cwd).
"""
import re


# Raw EEG formats mne can read natively, keyed by file extension (lowercase,
# without the leading dot). Extensions map to the mne.io.read_raw_* function
# name the caller should use, and the canonical BIDS source_format label.
EXTENSION_FORMAT_MAP = {
    "edf": ("read_raw_edf", "EDF"),
    "bdf": ("read_raw_bdf", "BDF"),
    "vhdr": ("read_raw_brainvision", "BrainVision"),
    "set": ("read_raw_eeglab", "EEGLAB"),
    "cnt": ("read_raw_cnt", "CNT"),
    "gdf": ("read_raw_gdf", "GDF"),
    "fif": ("read_raw_fif", "FIF"),
}

# Extensions that are companions to a primary file and shouldn't be scanned
# as their own recordings (BrainVision trio, EEGLAB .fdt companion).
COMPANION_EXTENSIONS = {"eeg", "vmrk", "fdt"}

# Extensions that commonly hold event/marker/annotation sidecar data in the
# wild (never authoritative BIDS files themselves -- just a signal during
# dataset scanning that a raw file likely has an external events source).
EVENT_SIDECAR_EXTENSIONS = {"csv", "tsv", "txt", "lab", "tse_agg", "tse_ag", "xlsx", "mat"}


def guess_format(extension: str):
    """Return (reader_function_name, bids_format_label) or (None, None)."""
    return EXTENSION_FORMAT_MAP.get(extension.lower(), (None, None))


def sanitize_label(value: str) -> str:
    """Strip everything but alphanumerics, per BIDS label rules.

    BIDS entity labels (sub-<label>, task-<label>, etc.) MUST be alphanumeric
    only -- no underscores, hyphens, or spaces. This is also how mne-bids
    derives a filename-safe task label from a human-readable TaskName.
    """
    return re.sub(r"[^A-Za-z0-9]", "", str(value))


def zero_pad_run(run) -> str:
    """BIDSPath zero-pads run/split to >=2 digits; mirror that for filenames
    or manifests built before a BIDSPath exists."""
    s = str(run)
    return s.zfill(2) if s.isdigit() else sanitize_label(s)
