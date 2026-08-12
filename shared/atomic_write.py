"""Atomic file writes for the precomputed CSV exports under Ref/.

dashboard_site re-reads these files periodically (a background refresh
loop, plus on-demand lazy loads) while the GDoc-updater pipeline
periodically regenerates them. A plain `open(path, "w")`/`df.to_csv(path)`
truncates the file immediately and writes it in place, so a reader that
opens the file mid-write can see a truncated or otherwise malformed row
set -- confirmed as the root cause of at least one "cannot handle a
non-unique multi-index!" crash (see
dashboard_site/api/league_store.py::_load_po_real_matchup_lookup's
docstring). Writing to a temp file in the same directory and swapping it
into place with os.replace() (atomic on POSIX, same filesystem) means a
reader only ever sees the old complete file or the new complete file,
never a partial one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable, IO


def atomic_write(
    path: Path,
    write_fn: Callable[[IO], None],
    mode: str = "w",
    newline: str | None = None,
) -> None:
    """Calls write_fn(file_handle) against a temp file in `path`'s own
    directory (same filesystem, required for os.replace to be atomic),
    then swaps it into place. `path`'s parent directory must already
    exist. On any failure, the temp file is cleaned up and the real path
    is left untouched."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, mode, newline=newline) as f:
            write_fn(f)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
