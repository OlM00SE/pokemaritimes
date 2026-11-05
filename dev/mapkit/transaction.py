"""Small rollback boundary for authoring commands that update several source files.

Declare the complete write set before changing anything. Exceptions (including Ctrl-C)
restore existing bytes and remove only the declared, previously absent directories.
This protects failed commands, not a killed process or power loss; keep using git.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import tempfile


def atomic_write(path, data):
    """Replace one file without exposing a truncated version if writing fails."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".mapkit-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def invalidate(project):
    for key in ("layouts", "map_names", "const_to_map", "script_labels"):
        project.__dict__.pop(key, None)


@contextmanager
def edit(project, files=(), new_dirs=()):
    """All-or-rollback source edits; paths are relative to the project root.

    New directories must not already exist, including orphaned authoring output.
    Nested boundaries are allowed (e.g. mapgen -> buildings -> interiors).
    """
    root = Path(project.root).resolve()

    def within(rel):
        path = (root / rel).resolve()
        if path == root or root not in path.parents:
            raise ValueError(f"authoring path is outside the project: {rel}")
        return path

    paths = list(dict.fromkeys(within(f) for f in files))
    dirs = list(dict.fromkeys(within(d) for d in new_dirs))
    for d in dirs:
        if d.exists():
            raise FileExistsError(f"refusing to overwrite existing directory: {d}")
    saved = {}
    for path in paths:
        if path.exists():
            st = path.stat()
            saved[path] = (path.read_bytes(), st.st_atime_ns, st.st_mtime_ns)
        else:
            saved[path] = None
    try:
        yield
    except BaseException as original:
        errors = []
        for path, old in saved.items():
            try:
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, old[0])
                    os.utime(path, ns=old[1:])
            except OSError as ex:
                errors.append(f"{path}: {ex}")
        for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
            try:
                if d.exists():
                    shutil.rmtree(d)
            except OSError as ex:
                errors.append(f"{d}: {ex}")
        if errors:
            raise RuntimeError("authoring rollback failed; restore these paths from git:\n"
                               + "\n".join(errors)) from original
        raise
    finally:
        invalidate(project)
