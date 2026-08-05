"""
ecco_common.cache — where downloaded ECCO granules live, and cache lookup.

Storage strategy (see design.md → Data Storage Strategy): cache-on-demand in a
project-local dir, reused across runs, never bulk-downloaded.

Layout:  <cache_root>/<ShortName>/<granule_filename>.nc
Default cache_root:  <project-root>/data/ecco   (override with env var ECCO_DATA_DIR)

Project root is derived from THIS FILE's location, not the caller's CWD, so the cache
always resolves to the real project `data/ecco` no matter which directory a skill is
run from. (This file lives at
  <project-root>/.claude/skills/ecco-common/ecco_common/cache.py
so the project root is four parents up from this file's directory.)
"""

import os

DEFAULT_SUBDIR = os.path.join("data", "ecco")


def project_root():
    """Absolute path to the project root, derived from this file's location.

    Layout: <root>/.claude/skills/ecco-common/ecco_common/cache.py
    -> root is os.path.dirname applied 5 times to __file__
       (cache.py -> ecco_common -> ecco-common -> skills -> .claude -> root).
    Does NOT depend on the current working directory.
    """
    here = os.path.dirname(os.path.abspath(__file__))          # .../ecco_common
    return os.path.abspath(os.path.join(here, "..", "..", "..", ".."))


def cache_root():
    """Return the cache root dir. Env ECCO_DATA_DIR overrides the project-local
    default (<project-root>/data/ecco), for users who want one shared cache across
    projects. The default is anchored to the project (via project_root()), NOT the
    caller's CWD, so loaders work regardless of where a skill is invoked from."""
    override = os.environ.get("ECCO_DATA_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(project_root(), DEFAULT_SUBDIR)


def collection_dir(short_name):
    """Directory for one collection's granules (created if missing)."""
    d = os.path.join(cache_root(), short_name)
    os.makedirs(d, exist_ok=True)
    return d


def cached_path(short_name, filename):
    """Full path where a given granule file is (or would be) cached."""
    return os.path.join(collection_dir(short_name), filename)


def is_cached(short_name, filename):
    """True if the granule is already downloaded (and non-empty)."""
    p = cached_path(short_name, filename)
    return os.path.exists(p) and os.path.getsize(p) > 0


# --- local cache index (enables OFFLINE reuse without a CMR round-trip) ------------
# We record, per (short_name, key), the granule filename we downloaded. A later run can
# resolve the filename from this index and skip CMR entirely if the file is present.
# `key` is a stable string: 'GEOMETRY' for the geometry, or the 'YYYY-MM' month.
import json


def index_path():
    return os.path.join(cache_root(), "cache_index.json")


def _read_index():
    p = index_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def record_in_index(short_name, key, filename):
    """Remember that (short_name, key) resolved to `filename`. Best-effort, atomic
    write (write to a temp file then os.replace) so a crash/concurrent run can't leave
    a half-written index. Re-reads immediately before writing to minimize (not fully
    eliminate) read-modify-write races."""
    idx = _read_index()
    idx.setdefault(short_name, {})[str(key)] = filename
    try:
        os.makedirs(cache_root(), exist_ok=True)
        tmp = index_path() + f".tmp.{os.getpid()}"
        with open(tmp, "w") as f:
            json.dump(idx, f, indent=2, sort_keys=True)
        os.replace(tmp, index_path())          # atomic on POSIX & Windows
    except OSError:
        pass


def _date_key_from_filename(filename):
    """Extract the time key from an ECCO granule filename, else None.
    Daily files carry '_YYYY-MM-DD_' → key 'YYYY-MM-DD'; monthly files carry
    '_YYYY-MM_' → key 'YYYY-MM'. Check daily FIRST (it's the more specific pattern;
    a monthly regex would match the 'YYYY-MM' prefix of a daily date)."""
    import re
    m = re.search(r"_(\d{4}-\d{2}-\d{2})_", filename)   # daily, more specific first
    if m:
        return m.group(1)
    m = re.search(r"_(\d{4}-\d{2})_", filename)          # monthly
    return m.group(1) if m else None


def backfill_index_from_disk(short_name):
    """Discover already-cached files for a collection and add any missing index
    entries, so files downloaded before the index existed (or by another tool) can be
    resolved offline. Geometry → key 'GEOMETRY'; monthly → 'YYYY-MM'; daily → 'YYYY-MM-DD'."""
    d = os.path.join(cache_root(), short_name)
    if not os.path.isdir(d):
        return
    for fn in os.listdir(d):
        if not fn.endswith(".nc"):
            continue
        if "GEOMETRY" in fn:
            key = "GEOMETRY"
        else:
            key = _date_key_from_filename(fn)
        if key and _read_index().get(short_name, {}).get(key) != fn:
            record_in_index(short_name, key, fn)


def lookup_cached(short_name, key):
    """Return the cached local path for (short_name, key) if resolvable offline; else
    None. Checks the index first, then (on miss) backfills from disk and retries — so
    pre-existing cached files are discovered without a CMR request."""
    idx = _read_index()
    filename = idx.get(short_name, {}).get(str(key))
    if filename and is_cached(short_name, filename):
        return cached_path(short_name, filename)
    # Miss: try discovering files already on disk, then look again.
    backfill_index_from_disk(short_name)
    filename = _read_index().get(short_name, {}).get(str(key))
    if filename and is_cached(short_name, filename):
        return cached_path(short_name, filename)
    return None
