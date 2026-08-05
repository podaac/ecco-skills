#!/usr/bin/env python3
"""
Automated regression suite for ecco_common (the shared loader/cache/access layer).

Locks in the behaviors hardened across three external-eval rounds so Recipe 2+ can
depend on them. Runs FULLY OFFLINE — `_http_json` and `_download` are monkeypatched
with synthetic CMR responses and fake files, and the cache is redirected to a temp dir
via ECCO_DATA_DIR. No network, no real granules, no NASA credentials needed.

Run with the venv python (no pytest required):
    .venv/bin/python .claude/skills/ecco-common/tests/test_ecco_common.py
It is also pytest-compatible:  pytest .claude/skills/ecco-common/tests/
Exit 0 if all pass, 1 otherwise.
"""
import os
import sys
import tempfile
import traceback

# Put ecco_common on the path (tests/ is one level below the package dir).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))

from ecco_common import access, cache, loaders  # noqa: E402


# --------------------------------------------------------------------------
# Synthetic CMR helpers
# --------------------------------------------------------------------------
def _archive_info(nc_name, size_bytes, with_sidecar_first=False):
    """Build an ArchiveAndDistributionInformation list like CMR's, optionally with the
    .sha512 sidecar listed BEFORE the .nc (the ordering that broke the size guard)."""
    nc = {"Name": nc_name, "SizeInBytes": size_bytes, "Size": size_bytes / 1e6,
          "SizeUnit": "MB", "Checksum": {"Value": "abc123", "Algorithm": "SHA-512"}}
    sidecar = {"Name": nc_name + ".sha512", "SizeInBytes": 193,
               "Size": 193 / 1e6, "SizeUnit": "MB"}
    return [sidecar, nc] if with_sidecar_first else [nc, sidecar]


def _item(nc_name, size_bytes, with_sidecar_first=False):
    """One CMR granule 'items' entry."""
    url = f"https://example.test/path/{nc_name}"
    return {
        "umm": {
            "GranuleUR": nc_name.replace(".nc", ""),
            "RelatedUrls": [
                {"Type": "GET DATA", "URL": url},
                {"Type": "VIEW RELATED INFORMATION", "URL": url + ".sha512"},
            ],
            "DataGranule": {
                "ArchiveAndDistributionInformation":
                    _archive_info(nc_name, size_bytes, with_sidecar_first)
            },
        }
    }


def make_http_json(pages):
    """Return a fake _http_json that yields `pages` (list of items-lists) in sequence
    via search-after tokens, recording the token order it was called with."""
    calls = {"tokens": []}

    def fake(url, search_after=None):
        calls["tokens"].append(search_after)
        idx = 0 if search_after is None else int(search_after)
        items = pages[idx] if idx < len(pages) else []
        nxt = str(idx + 1) if idx + 1 < len(pages) else None
        return {"items": items}, nxt

    fake.calls = calls
    return fake


# --------------------------------------------------------------------------
# Test harness (tiny; avoids a pytest dependency)
# --------------------------------------------------------------------------
class Ctx:
    """Per-test context: fresh temp cache dir + saved/restored monkeypatches."""
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name
        self._saved = {}
        self._prev_env = os.environ.get("ECCO_DATA_DIR")
        os.environ["ECCO_DATA_DIR"] = self.data_dir

    def patch(self, mod, name, value):
        self._saved[(mod, name)] = getattr(mod, name)
        setattr(mod, name, value)

    def close(self):
        for (mod, name), val in self._saved.items():
            setattr(mod, name, val)
        if self._prev_env is None:
            os.environ.pop("ECCO_DATA_DIR", None)
        else:
            os.environ["ECCO_DATA_DIR"] = self._prev_env
        access._resolved_ids.clear()
        self._tmp.cleanup()


def _fake_download_factory(ctx):
    """A fake _download that just writes a small placeholder file to dest."""
    def fake_download(url, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(b"NETCDF_PLACEHOLDER")
    return fake_download


TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def eq(a, b, msg=""):
    assert a == b, f"{msg}  (got {a!r}, expected {b!r})"


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc:
        return True
    raise AssertionError(f"expected {exc.__name__} but no error raised")


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
@test
def test_size_from_nc_not_sidecar_even_if_sidecar_first(ctx):
    """Size guard bug: pick the .nc entry by name, not the first MB entry."""
    ctx.patch(access, "_http_json",
              make_http_json([[_item("OCEAN_X_2000-01_llc0090.nc", 30_000_000,
                                     with_sidecar_first=True)]]))
    gs = access.granules_for("ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4",
                             start="2000-01-14T00:00:00Z", end="2000-01-16T00:00:00Z")
    eq(len(gs), 1, "one granule")
    assert abs(gs[0]["size_mb"] - 28.6) < 0.5, f"size should be ~28.6 MB, got {gs[0]['size_mb']}"
    eq(gs[0]["checksum_algorithm"], "SHA-512", "checksum captured")


@test
def test_pagination_follows_search_after(ctx):
    """CMR pagination: all pages retrieved, tokens passed in order."""
    pages = [[_item(f"F_{i}_2000-01.nc", 1_000_000)] for i in range(3)]
    fake = make_http_json(pages)
    ctx.patch(access, "_http_json", fake)
    gs = access.granules_for("ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4")
    eq(len(gs), 3, "all 3 pages retrieved")
    eq(fake.calls["tokens"], [None, "1", "2"], "search-after tokens in sequence")


@test
def test_size_guard_blocks_large_total(ctx):
    """check_download_size raises when the TOTAL exceeds the threshold."""
    granules = [{"filename": f"f{i}.nc", "size_mb": 100.0} for i in range(20)]  # 2 GB
    raises(RuntimeError, access.check_download_size,
           "ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4", granules, assume_yes=False)


@test
def test_size_guard_allows_small_and_assume_yes(ctx):
    """Small total passes; assume_yes overrides a large total."""
    small = [{"filename": "a.nc", "size_mb": 30.0}]
    access.check_download_size("X", small, assume_yes=False)          # no raise
    big = [{"filename": f"f{i}.nc", "size_mb": 100.0} for i in range(20)]
    access.check_download_size("X", big, assume_yes=True)             # overridden


@test
def test_size_guard_unknown_size_trips(ctx):
    """A granule with no size can't be size-checked → guard trips unless assume_yes."""
    granules = [{"filename": "a.nc", "size_mb": None}]
    raises(RuntimeError, access.check_download_size, "X", granules, assume_yes=False)
    access.check_download_size("X", granules, assume_yes=True)        # overridden


@test
def test_month_and_day_midpoint_ranges(ctx):
    """Selectors query mid-interval to dodge edge overlap."""
    s, e = access.month_midpoint_range("2000-01")
    assert s.startswith("2000-01-14") and e.startswith("2000-01-16"), (s, e)
    s, e = access.day_midpoint_range("2000-01-15")
    assert "T11:00:00" in s and "T13:00:00" in e, (s, e)


@test
def test_date_key_extraction_daily_and_monthly(ctx):
    """Backfill key regex handles BOTH daily YYYY-MM-DD and monthly YYYY-MM."""
    eq(cache._date_key_from_filename("OCEAN_VELOCITY_day_mean_2000-01-15_ECCO.nc"),
       "2000-01-15", "daily key")
    eq(cache._date_key_from_filename("OCEAN_TEMP_mon_mean_2000-01_ECCO.nc"),
       "2000-01", "monthly key")
    eq(cache._date_key_from_filename("GRID_GEOMETRY_ECCO.nc"), None, "no date")


@test
def test_cache_backfill_discovers_existing_files(ctx):
    """Files already on disk (no index) are discovered and become offline-resolvable."""
    sn = "ECCO_L4_OCEAN_VEL_LLC0090GRID_DAILY_V4R4"
    d = cache.collection_dir(sn)
    fn = "OCEAN_VELOCITY_day_mean_2000-01-15_ECCO_V4r4_native_llc0090.nc"
    with open(os.path.join(d, fn), "wb") as f:
        f.write(b"x")
    # index is empty; lookup should backfill from disk and resolve
    path = cache.lookup_cached(sn, "2000-01-15")
    assert path is not None and path.endswith(fn), path


@test
def test_cache_index_atomic_write_and_roundtrip(ctx):
    """record_in_index persists and reads back; no .tmp leftovers."""
    cache.record_in_index("COLL", "2000-01", "file.nc")
    eq(cache._read_index()["COLL"]["2000-01"], "file.nc", "roundtrip")
    leftovers = [f for f in os.listdir(cache.cache_root()) if ".tmp." in f]
    eq(leftovers, [], "no temp files left behind")


@test
def test_load_field_selector_validation(ctx):
    """load_field rejects both/neither/empty selectors before any I/O."""
    sn = "ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4"
    raises(ValueError, loaders.load_field, sn)                                  # neither
    raises(ValueError, loaders.load_field, sn, months=["2000-01"], start="x")   # both
    raises(ValueError, loaders.load_field, sn, months=[])                       # empty
    raises(ValueError, loaders.load_field, sn, days=[])                         # empty


@test
def test_live_shortname_resolution_via_cmr(ctx):
    """concept_id_for resolves an unknown ShortName through the collections endpoint."""
    def fake(url, search_after=None):
        assert "collections" in url, "should hit the collections endpoint"
        return {"items": [{"meta": {"concept-id": "C999-TEST"}}]}, None
    ctx.patch(access, "_http_json", fake)
    eq(access.concept_id_for("ECCO_L4_SOME_NEW_COLLECTION_V4R4"), "C999-TEST")


@test
def test_offline_reuse_after_backfill_no_network(ctx):
    """A cached monthly file resolves with NO CMR call (network would raise)."""
    sn = "ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4"
    d = cache.collection_dir(sn)
    fn = "OCEAN_TEMPERATURE_SALINITY_mon_mean_2000-01_ECCO_V4r4_native_llc0090.nc"
    with open(os.path.join(d, fn), "wb") as f:
        f.write(b"x")

    def boom(*a, **k):
        raise AssertionError("network should NOT be called for a cached file")
    ctx.patch(access, "_http_json", boom)
    path = cache.lookup_cached(sn, "2000-01")
    assert path is not None and path.endswith(fn), path


@test
def test_whole_request_size_guard_across_days(ctx):
    """The guard sees the WHOLE multi-day request, not one day at a time."""
    sn = "ECCO_L4_OCEAN_VEL_LLC0090GRID_DAILY_V4R4"
    # each day -> one 100 MB granule; 20 days = 2 GB -> must trip
    def fake(url, search_after=None):
        # date is in the temporal= param; just return a 100 MB granule named for it
        return {"items": [_item("OCEAN_VELOCITY_day_mean_2000-01-01_ECCO.nc",
                                100_000_000)]}, None
    ctx.patch(access, "_http_json", fake)
    ctx.patch(access, "_download", _fake_download_factory(ctx))
    days = [f"2000-01-{d:02d}" for d in range(1, 21)]
    raises(RuntimeError, loaders.load_field, sn, days=days, assume_yes=False)


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
def main():
    print("=" * 64)
    print("ecco_common regression suite (offline)")
    print("=" * 64)
    passed = failed = 0
    for fn in TESTS:
        ctx = Ctx()
        try:
            fn(ctx)
            print(f"  [PASS] {fn.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
        finally:
            ctx.close()
    print("=" * 64)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
