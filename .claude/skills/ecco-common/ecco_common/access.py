"""
ecco_common.access — find and download ECCO granules from NASA PO.DAAC.

We use CMR directly (query granule access_urls, then download the file) rather than
ecco_access's auto-resolution, which was unreliable in 0.3.1 (wrong filenames, 75 GB
over-estimates; see design.md → Data Access Pattern). Auth uses the user's ~/.netrc
Earthdata credentials.

Public helpers:
  granules_for(short_name, start=None, end=None)   -> list of granule dicts
  ensure_granule(short_name, granule)              -> local cached path (download if needed)
  ensure_granules(short_name, granules, ...)       -> list of local paths (size-guarded)
"""

import os
import sys
import urllib.request
import urllib.error

from . import cache

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"

CMR_COLLECTIONS = "https://cmr.earthdata.nasa.gov/search/collections.umm_json"

# Known collection concept IDs (verified in CMR; see design.md Data Access tables).
# Unknown ShortNames are resolved live via CMR (see concept_id_for), so this map is a
# fast-path cache, not an allow-list.
CONCEPT_IDS = {
    "ECCO_L4_GEOMETRY_LLC0090GRID_V4R4": "C2013557893-POCLOUD",
    # --- monthly ---
    "ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4": "C1991543732-POCLOUD",
    "ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4": "C1991543735-POCLOUD",
    "ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4": "C1991543728-POCLOUD",
    "ECCO_L4_SSH_LLC0090GRID_MONTHLY_V4R4": "C1991543813-POCLOUD",
    "ECCO_L4_OCEAN_3D_VOLUME_FLUX_LLC0090GRID_MONTHLY_V4R4": "C1991543739-POCLOUD",
    "ECCO_L4_BOLUS_LLC0090GRID_MONTHLY_V4R4": "C1991543745-POCLOUD",
    "ECCO_L4_OCEAN_3D_TEMPERATURE_FLUX_LLC0090GRID_MONTHLY_V4R4": "C1991543740-POCLOUD",
    "ECCO_L4_OCEAN_3D_SALINITY_FLUX_LLC0090GRID_MONTHLY_V4R4": "C1991543752-POCLOUD",
    "ECCO_L4_STRESS_LLC0090GRID_MONTHLY_V4R4": "C1991543760-POCLOUD",
    # --- daily (verified in CMR 2026-07-25; needed by the geostrophic tutorial) ---
    "ECCO_L4_OCEAN_VEL_LLC0090GRID_DAILY_V4R4": "C1991543808-POCLOUD",
    "ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_DAILY_V4R4": "C1991543727-POCLOUD",
    "ECCO_L4_TEMP_SALINITY_LLC0090GRID_DAILY_V4R4": "C1991543736-POCLOUD",
    "ECCO_L4_SSH_LLC0090GRID_DAILY_V4R4": "C1991543744-POCLOUD",
}

# Cache for concept IDs resolved live from CMR this session.
_resolved_ids = {}


def concept_id_for(short_name):
    """Resolve a collection's concept ID: fast-path from CONCEPT_IDS, else query CMR
    live (so any valid ECCO ShortName works, not just the hardcoded ones). Raises
    ValueError if CMR knows no such collection."""
    if short_name in CONCEPT_IDS:
        return CONCEPT_IDS[short_name]
    if short_name in _resolved_ids:
        return _resolved_ids[short_name]
    url = CMR_COLLECTIONS + f"?short_name={short_name}&page_size=1"
    try:
        data, _ = _http_json(url)
        items = data.get("items", [])
        cid = items[0]["meta"]["concept-id"] if items else None
    except Exception as e:  # network / parse
        raise ValueError(
            f"Could not resolve ShortName '{short_name}' via CMR ({e}). "
            f"Check the name, or add it to CONCEPT_IDS."
        )
    if not cid:
        raise ValueError(f"CMR knows no collection with ShortName '{short_name}'.")
    _resolved_ids[short_name] = cid
    return cid

# Ask-before-downloading threshold (MB). A single month is well under this; a
# multi-year request can blow past it, so we stop and let the caller confirm.
SIZE_WARN_MB = 1024.0


def _http_json(url, search_after=None):
    """GET a CMR JSON page. Returns (parsed_json, next_search_after_token).
    Uses CMR's stable `CMR-Search-After` pagination header."""
    import json
    headers = {"Accept": "application/json"}
    if search_after:
        headers["CMR-Search-After"] = search_after
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read().decode())
        nxt = r.headers.get("CMR-Search-After")
    return body, nxt


def granules_for(short_name, start=None, end=None, page_size=200):
    """Query CMR for granules in a collection, optionally within a temporal range.

    start/end are ISO strings (e.g. '2000-01-01', '2000-01-31T23:59:59Z') or None.
    Returns a list of dicts: {granule_ur, filename, url, size_mb}.
    """
    concept_id = concept_id_for(short_name)   # fast-path map, else live CMR lookup
    params = [f"collection_concept_id={concept_id}", f"page_size={page_size}"]
    if start or end:
        lo = start or ""
        hi = end or ""
        params.append(f"temporal={lo},{hi}")
    url = CMR_GRANULES + "?" + "&".join(params)

    # Page through ALL results via CMR-Search-After (a single page caps at page_size,
    # which would silently truncate a multi-year/daily request). Keep going until a
    # page returns no items or CMR stops issuing a search-after token.
    out = []
    search_after = None
    max_pages = 10000  # safety backstop
    for _ in range(max_pages):
        data, search_after = _http_json(url, search_after=search_after)
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            umm = item.get("umm", {})
            gid = umm.get("GranuleUR", "")
            dl_url = None
            for ru in umm.get("RelatedUrls", []):
                if ru.get("Type") == "GET DATA" and ru.get("URL", "").endswith(".nc"):
                    dl_url = ru["URL"]
                    break
            if not dl_url:
                continue
            filename = dl_url.rsplit("/", 1)[-1]
            # Size: match the archive entry whose Name is EXACTLY the NetCDF file.
            # A CMR record also lists the `.sha512` checksum sidecar (a few hundred
            # bytes) — taking the "first MB entry" can grab the sidecar and wildly
            # under-report size, defeating the download guard. Prefer SizeInBytes as
            # canonical; keep the checksum for later verification.
            size_mb = None
            checksum = None
            checksum_alg = None
            ai = umm.get("DataGranule", {}).get("ArchiveAndDistributionInformation", [])
            entry = next((a for a in ai if a.get("Name") == filename), None)
            if entry is not None:
                if entry.get("SizeInBytes") is not None:
                    size_mb = float(entry["SizeInBytes"]) / (1024.0 * 1024.0)
                elif entry.get("SizeUnit") == "MB" and entry.get("Size") is not None:
                    size_mb = float(entry["Size"])
                ck = entry.get("Checksum") or {}
                checksum = ck.get("Value")
                checksum_alg = ck.get("Algorithm")
            out.append({
                "granule_ur": gid,
                "filename": filename,
                "url": dl_url,
                "size_mb": size_mb,
                "checksum": checksum,
                "checksum_algorithm": checksum_alg,
            })
        if not search_after:
            break
    return out


def month_midpoint_range(year_month):
    """Given 'YYYY-MM', return (start, end) ISO strings bracketing the MIDDLE of that
    month. Monthly-mean granules carry time bounds that meet at month edges, so an
    edge-aligned query (e.g. 2000-01-01..2000-01-31) also matches the ADJACENT month's
    granule. Querying mid-month returns exactly the one intended month. Verified
    2026-07-23. See design.md → Data Access (temporal overlap gotcha)."""
    y, m = year_month.split("-")
    return (f"{y}-{m}-14T00:00:00Z", f"{y}-{m}-16T00:00:00Z")


def granules_for_month(short_name, year_month):
    """Granules for exactly one calendar month 'YYYY-MM' (avoids the edge-overlap
    that pulls in the neighbouring month)."""
    start, end = month_midpoint_range(year_month)
    return granules_for(short_name, start=start, end=end)


def day_midpoint_range(year_month_day):
    """Given 'YYYY-MM-DD', return (start, end) ISO strings bracketing NOON of that day.
    Daily-mean granules' time bounds meet at midnight, so a query starting exactly at
    00:00:00Z also matches the PREVIOUS day's granule (verified live 2026-07-25).
    Querying around noon returns exactly the one intended day."""
    return (f"{year_month_day}T11:00:00Z", f"{year_month_day}T13:00:00Z")


def granules_for_day(short_name, year_month_day):
    """Granules for exactly one calendar day 'YYYY-MM-DD' (avoids the midnight-edge
    overlap that pulls in the adjacent day). Filters to filenames containing the date,
    as a belt-and-suspenders guard against any residual overlap."""
    start, end = day_midpoint_range(year_month_day)
    gs = granules_for(short_name, start=start, end=end)
    # Defensive filename filter: keep only granules whose filename carries this date.
    matched = [g for g in gs if year_month_day in g["filename"]]
    return matched if matched else gs


def _download(url, dest):
    """Download one file to dest using ~/.netrc Earthdata auth, following redirects.

    NASA Earthdata bounces the request through a URS login redirect. `requests` with
    a session picks up ~/.netrc credentials and re-sends auth across the redirect
    chain (plain urllib does not, and 401s). Requires an Earthdata Login entry in
    ~/.netrc for machine urs.earthdata.nasa.gov.
    """
    import requests

    tmp = dest + ".part"
    try:
        with requests.Session() as s:
            # trust_env=True (default) makes requests read ~/.netrc automatically
            with s.get(url, stream=True, timeout=300, allow_redirects=True) as r:
                if r.status_code == 401:
                    raise RuntimeError(
                        "401 Unauthorized from Earthdata. Check that ~/.netrc has a "
                        "valid entry for machine urs.earthdata.nasa.gov "
                        "(login + password). See design.md → Data Access (credentials)."
                    )
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if chunk:
                            f.write(chunk)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def ensure_granule(short_name, granule, log=print):
    """Return local path for one granule dict, downloading if not cached."""
    fn = granule["filename"]
    if cache.is_cached(short_name, fn):
        log(f"  [cache] using {short_name}/{fn}")
        return cache.cached_path(short_name, fn)
    dest = cache.cached_path(short_name, fn)
    size = granule.get("size_mb")
    size_str = f" ({size:.0f} MB)" if size else ""
    log(f"  [download] {short_name}/{fn}{size_str} ...")
    _download(granule["url"], dest)
    log(f"  [done] cached at {dest}")
    return dest


def check_download_size(short_name, granules, assume_yes=False):
    """Size-aware guard over a set of granules. Sums the size of those NOT already
    cached; if it exceeds SIZE_WARN_MB, raise unless assume_yes. Call this ONCE over a
    whole request (across all requested months/days) — guarding per-granule or per-day
    would let a large multi-file request slip through one small file at a time.
    Also flags granules with unknown size so a missing size can't hide a big download."""
    to_get = [g for g in granules if not cache.is_cached(short_name, g["filename"])]
    n_unknown = sum(1 for g in to_get if not g.get("size_mb"))
    total_mb = sum(g.get("size_mb") or 0 for g in to_get)
    if total_mb > SIZE_WARN_MB and not assume_yes:
        raise RuntimeError(
            f"This would download {total_mb:.0f} MB ({len(to_get)} files) for "
            f"{short_name}. That's a lot — confirm before proceeding "
            f"(pass assume_yes=True / --yes). Consider a shorter time range."
        )
    if n_unknown and not assume_yes:
        raise RuntimeError(
            f"{n_unknown} of {len(to_get)} {short_name} granules report no size — "
            f"cannot size-check safely. Pass assume_yes=True to proceed anyway."
        )


def ensure_granules(short_name, granules, log=print, assume_yes=False):
    """Ensure a list of granules is cached. Applies the size-aware guard (see
    check_download_size) over this batch, then downloads. When the caller has already
    size-checked the whole request, pass assume_yes=True to skip the re-check."""
    check_download_size(short_name, granules, assume_yes=assume_yes)
    return [ensure_granule(short_name, g, log=log) for g in granules]
