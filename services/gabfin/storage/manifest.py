"""Atomic manifest files; a manifest is an index, not the authority.

A manifest is written last and read first. If a write is interrupted the
manifest still points at the previous state, so a reader never sees a
half-written series described as complete.
"""
from pathlib import Path

from gabfin.contracts.tape import TapeManifest

MANIFEST_NAME = 'manifest.json'


def manifest_path(directory: Path) -> Path:
    """Where the manifest for one series directory lives."""
    return directory / MANIFEST_NAME


def write_manifest(path: Path, manifest: TapeManifest) -> Path:
    """Replace the manifest atomically so a reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(manifest.model_dump_json(indent=2), encoding='utf-8')
    temporary.replace(path)
    return path


def read_manifest(path: Path) -> TapeManifest:
    """Read and validate a manifest; a missing or malformed file is an error.

    The reader never guesses. A missing manifest means the series was never
    written, and a malformed one means the index cannot be trusted.
    """
    if not path.exists():
        raise FileNotFoundError(f'No tape manifest at {path}')
    return TapeManifest.model_validate_json(path.read_text(encoding='utf-8'))
