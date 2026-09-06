"""
Getting the index into the container, and new indexes back out to Stratus.

Two directions, and they authenticate differently for a reason that is not
obvious:

  READ  (startup)  plain HTTPS GET, no credentials.
  WRITE (re-index) Catalyst SDK, credentials taken from the request.

The asymmetry is forced. zcatalyst_sdk.initialize() builds its credential
from headers Catalyst injects into an inbound request (X-ZC-Admin-Cred-Token
and friends — see credentials.py in the SDK). At startup there is no inbound
request, so there is nothing to build a credential from. An index the
container cannot read until someone calls it is useless: every new instance
would serve errors until its first request, which is exactly the cold-start
behaviour AppSail's 30s ceiling punishes.

So the objects are world-readable and the bucket only gates writes. That is
a deliberate exposure, and it is an acceptable one: the index is derived
from kfoundation.org's public talk archive, it contains no user data, and
publishing it makes the evaluation numbers independently checkable, which
for this project is a feature. Do not copy this pattern to an index built
over private documents — there the answer is a signed URL fetched by a
short-lived job, not public read.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

BUCKET_URL = os.environ.get(
    "INDEX_BUCKET_URL", "https://krishnamurti-index-development.zohostratus.in"
)
BUCKET_NAME = os.environ.get("INDEX_BUCKET_NAME", "krishnamurti-index")

# manifest.json first: it carries the corpus fingerprint, so it is what
# decides whether the rest needs downloading at all.
OBJECTS = ("manifest.json", "vectors.f16.npy", "chunks.jsonl.gz", "vocabulary.json")


def _remote_manifest() -> dict | None:
    try:
        with urllib.request.urlopen(f"{BUCKET_URL}/manifest.json", timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def ensure_index(index_dir: Path | str) -> dict:
    """
    Make index_dir hold the index Stratus currently advertises.

    Skips the download when the local fingerprint already matches, which is
    what makes a redeploy cheap and a re-index expensive — the right way
    round. Returns a report the agent can put in its evidence log.
    """
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    local_manifest = index_dir / "manifest.json"

    remote = _remote_manifest()
    if remote is None:
        if local_manifest.exists():
            # Stratus being unreachable is not a reason to throw away a
            # working index; serve the one on disk and say so.
            return {"downloaded": False, "reason": "stratus unreachable, using local copy"}
        raise RuntimeError(
            f"no local index and {BUCKET_URL}/manifest.json is unreachable — "
            "the container cannot serve anything until one of those is fixed"
        )

    if local_manifest.exists():
        current = json.loads(local_manifest.read_text())
        if current.get("corpus_fingerprint") == remote.get("corpus_fingerprint"):
            return {"downloaded": False, "reason": "fingerprint already current",
                    "corpus_fingerprint": current.get("corpus_fingerprint")}

    t0 = time.time()
    total = 0
    for name in OBJECTS:
        # Download beside the target and rename, so an interrupted fetch
        # leaves the previous index intact rather than a half-written file
        # that fails a shape check three minutes later.
        tmp = index_dir / f".{name}.partial"
        with urllib.request.urlopen(f"{BUCKET_URL}/{name}", timeout=300) as r:
            tmp.write_bytes(r.read())
        tmp.rename(index_dir / name)
        total += (index_dir / name).stat().st_size

    return {
        "downloaded": True,
        "objects": len(OBJECTS),
        "bytes": total,
        "seconds": round(time.time() - t0, 1),
        "corpus_fingerprint": remote.get("corpus_fingerprint"),
    }


def _bucket(req):
    """
    The SDK bucket handle, authenticated as the caller.

    req is the inbound request; the SDK reads Catalyst's injected credential
    headers off it. This only works from inside a deployed AppSail — running
    it locally raises CatalystCredentialError('Admin credential type is
    unknown'), which is the correct failure rather than something to paper
    over.
    """
    import zcatalyst_sdk  # imported lazily: local dev must not need it

    return zcatalyst_sdk.initialize(req=req).stratus().bucket(BUCKET_NAME)


def initiate_multipart(req, key: str) -> dict:
    """Start a multipart upload and return the id the parts will carry."""
    res = _bucket(req).initiate_multipart_upload(key)
    # The SDK returns the raw API response; the id lives under different
    # keys depending on shape, so pull it defensively rather than assume.
    upload_id = None
    if isinstance(res, dict):
        upload_id = res.get("upload_id") or res.get("uploadId") or (
            res.get("data", {}).get("upload_id") if isinstance(res.get("data"), dict) else None
        )
    if not upload_id:
        raise RuntimeError(f"could not find upload_id in initiate response: {str(res)[:300]}")
    return {"key": key, "upload_id": upload_id}


def upload_part(req, key: str, upload_id: str, part_number: int, body: bytes) -> dict:
    """
    Upload one part.

    Returns the sha256 of exactly the bytes Stratus was handed, so the
    caller can compare it against what it sent. A part that arrives
    truncated would otherwise assemble into a corrupt index that only
    fails later, during evaluation, looking like a retrieval regression.
    """
    ok = _bucket(req).upload_part(key, upload_id, body, part_number, overwrite=True)
    return {
        "key": key,
        "part_number": part_number,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "ok": bool(ok),
    }


def complete_multipart(req, key: str, upload_id: str) -> dict:
    """Assemble the parts into the finished object."""
    bucket = _bucket(req)
    ok = bucket.complete_multipart_upload(key, upload_id, overwrite=True)
    summary = None
    try:
        summary = bucket.get_multipart_upload_summary(key, upload_id)
    except Exception as e:  # summary is evidence, not a precondition
        summary = f"unavailable: {type(e).__name__}: {e}"
    return {"key": key, "upload_id": upload_id, "ok": bool(ok), "summary": summary}


def put_object(req, key: str, body: bytes) -> dict:
    """
    Write one index object to Stratus, authenticated as the caller.

    Single-shot, so only for the small objects — manifest.json and
    vocabulary.json. The large ones must go through multipart or they will
    exceed AppSail's 30s request ceiling on any ordinary uplink.
    """
    bucket = _bucket(req)
    t0 = time.time()
    result = bucket.put_object(key, body, {"overwrite": "true"})
    return {
        "key": key,
        "bytes": len(body),
        "seconds": round(time.time() - t0, 1),
        "result": result if isinstance(result, (bool, dict)) else str(result),
    }
