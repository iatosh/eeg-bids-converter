"""Shared helpers for the eeg-bids-converter skill scripts.

Not a standalone entry point: imported by the other scripts/*.py files.
Pure stdlib only, so it never needs its own PEP 723 dependency block; it
just has to sit next to the scripts that import it (uv puts the script's
own directory on sys.path[0], so `import _common` works regardless of cwd).
"""
import re


# The four formats BIDS accepts for raw EEG, keyed by lowercase extension.
# Reading is not in this table: mne.io.read_raw dispatches by extension and
# covers far more than these. This only answers "may the source file be copied
# through as-is, or must it be converted on write".
BIDS_FORMATS = {
    "edf": "EDF",
    "bdf": "BDF",
    "vhdr": "BrainVision",
    "set": "EEGLAB",
}

# Extensions mne.io.read_raw dispatches on. Scanning asks a different question
# from writing: "is this plausibly a recording", not "may it be copied through".
# Kept as a plain set so inspect_dataset.py stays dependency-free; it only ever
# decides what to print, and convert_recording.py hands the file to mne either
# way. A format missing here is reported as unreadable but still converts.
READABLE_EXTENSIONS = {
    "edf", "bdf", "vhdr", "set", "cnt", "gdf", "fif",      # the common ones
    "cdt", "mff", "lay", "nxe", "data", "nedf", "eeg",     # curry, egi, persyst,
                                                            # eximia, nicolet, nedf,
                                                            # nihon kohden
}

# Extensions that are companions to a primary file and shouldn't be scanned
# as their own recordings (BrainVision trio, EEGLAB .fdt companion).
COMPANION_EXTENSIONS = {"eeg", "vmrk", "fdt"}

# Extensions that commonly hold event/marker/annotation sidecar data in the
# wild (never authoritative BIDS files themselves: just a signal during
# dataset scanning that a raw file likely has an external events source).
EVENT_SIDECAR_EXTENSIONS = {"csv", "tsv", "txt", "lab", "tse_agg", "tse_ag", "xlsx", "mat"}


def bids_format(extension: str):
    """Return the BIDS format label for this extension, or None if BIDS does
    not accept it and the recording must be converted on write."""
    return BIDS_FORMATS.get(extension.lower())


def sanitize_label(value: str) -> str:
    """Strip everything but alphanumerics, per BIDS label rules.

    BIDS entity labels (sub-<label>, task-<label>, etc.) MUST be alphanumeric
    only: no underscores, hyphens, or spaces. This is also how mne-bids
    derives a filename-safe task label from a human-readable TaskName.
    """
    return re.sub(r"[^A-Za-z0-9]", "", str(value))

