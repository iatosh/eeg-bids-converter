# Skill for Organizing EEG Data to BIDS Format

## Overview

Specialized toolkit for AI agents to automate the organization of EEG datasets into the Brain Imaging Data Structure (BIDS) compliant format. Ensures standardized data hierarchy and metadata for reproducible neuroimaging research.

## Installation

1. Clone or download this repository: `eeg-bids-converter`.
2. Place the folder into your agent's skills directory.
3. Ensure Python 3.x is installed with necessary dependencies (e.g., `mne`, `pandas`, `bids`).

## How it Works

The skill operates according to the [BIDS EEG Specification](https://bids-specification.readthedocs.io/en/stable/modality-specific-files/electroencephalography.html), ensuring data is organized as `sub-XX/ses-XX/eeg/`.

### Workflow

1. **Analysis**: Agent inspects raw files and current metadata.
2. **Conversion**: `convert_recording.py` moves files to the standard BIDS hierarchy.
3. **Metadata Generation**: `write_bids_metadata.py` creates required JSON sidecars.
4. **Refinement**: `patch_sidecar.py` updates specific fields to match precise experimental parameters.
5. **Validation**: `validate_bids.py` verifies final structure against official BIDS rules.

### Agent Behavior

- **Ambiguity**: If mapping is unclear (e.g., missing subject IDs or ambiguous session labels), agent asks user for clarification.
- **Missing Data**: Agent identifies missing mandatory BIDS fields and prompts user to provide them.
- **Correction**: If validation fails, agent analyzes errors and applies fixes via `patch_sidecar.py`.

Usage: Invoke via `/eeg-bids-converter`.

## License

MIT License
