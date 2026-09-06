#!/usr/bin/env python3
"""
Push a packed index to Stratus through the running AppSail.

This is the step that makes the agent's loop a loop. Everything else it
does — re-chunk, re-embed, evaluate, report — is worthless if delivering
the result needs a human to open a console and click Upload, because then
"re-index and evaluate" is not something the agent can actually run. That
is the same defect that disqualified QuickML's Knowledge Base, and it
would have been embarrassing to reproduce it one layer down.

Why it goes through the app rather than straight to Stratus: the Stratus
API wants an OAuth access token, and the Catalyst CLI token is not one
(neither Zoho-oauthtoken nor Zoho-ticket authenticates it). The SDK builds
its credential from headers Catalyst injects into an inbound request, so
only code already running inside the platform holds one. The app is inside;
this script is not.

Why multipart: AppSail kills a request at 30 seconds. vectors.f16.npy is
126 MB. Parts are sized to land well inside that budget even on a slow
uplink, and every part's sha256 is checked against what the server says it
received, because a silently truncated part assembles into an index that
fails much later, during evaluation, wearing the costume of a retrieval
regression.

    python3 ingest/push_index.py --dist dist/ --url https://... --token "$INDEX_PUSH_TOKEN"
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import urllib.error
import urllib.request

# Small enough that one part fits inside AppSail's 30s ceiling on a modest
# uplink (8 MB needs ~2.6 Mbit/s sustained to make it), large enough that a
# 126 MB object is ~16 parts rather than hundreds of round trips.
PART_SIZE = 8 * 1024 * 1024

# Below this, one request is fine and multipart is just overhead.
SINGLE_SHOT_MAX = 4 * 1024 * 1024

RETRIES = 3


def _request(method: str, url: str, token: str, body: bytes | None = None,
             timeout: int = 120) -> dict:
    req = urllib.request.Request(url, method=method, data=body)
    req.add_header("x-index-token", token)
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        import json
        return json.loads(r.read().decode() or "{}")


def _with_retries(label: str, fn):
    """
    Retry transient failures only.

    A 403 or 400 is a configuration mistake and retrying it just prints the
    same thing three times; a timeout or 5xx is worth another go, since the
    whole reason for parts is that this runs near a hard time limit.
    """
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:200]
            if e.code in (400, 403, 503):
                raise SystemExit(f"{label}: HTTP {e.code} — {detail}")
            last = f"HTTP {e.code} — {detail}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < RETRIES:
            wait = 2 ** attempt
            print(f"    {label}: {last}; retrying in {wait}s", flush=True)
            time.sleep(wait)
    raise SystemExit(f"{label}: giving up after {RETRIES} attempts — {last}")


def push_small(path: Path, base: str, token: str) -> None:
    body = path.read_bytes()
    _with_retries(path.name, lambda: _request("PUT", f"{base}/admin/index/{path.name}", token, body))
    print(f"  {path.name}: {len(body) / 1e6:.1f} MB in one request")


def push_multipart(path: Path, base: str, token: str) -> None:
    size = path.stat().st_size
    parts = (size + PART_SIZE - 1) // PART_SIZE
    print(f"  {path.name}: {size / 1e6:.1f} MB in {parts} parts")

    started = _with_retries(
        f"{path.name} initiate",
        lambda: _request("POST", f"{base}/admin/index/{path.name}/initiate", token, b""),
    )
    upload_id = started["upload_id"]

    t0 = time.time()
    with path.open("rb") as fh:
        for n in range(1, parts + 1):
            chunk = fh.read(PART_SIZE)
            expected = hashlib.sha256(chunk).hexdigest()
            url = f"{base}/admin/index/{path.name}/part/{n}?upload_id={upload_id}"
            res = _with_retries(
                f"{path.name} part {n}",
                lambda u=url, c=chunk: _request("PUT", u, token, c),
            )
            # The server hashes what Stratus was actually handed. A mismatch
            # means the body was truncated in flight, which must stop the
            # push rather than be assembled into a corrupt object.
            if res.get("sha256") != expected:
                raise SystemExit(
                    f"{path.name} part {n}: checksum mismatch — sent {expected[:12]}, "
                    f"server stored {str(res.get('sha256'))[:12]}"
                )
            done = n * PART_SIZE
            rate = min(done, size) / max(time.time() - t0, 0.001) / 1e6
            print(f"    part {n}/{parts} ok ({rate:.1f} MB/s)", flush=True)

    _with_retries(
        f"{path.name} complete",
        lambda: _request("POST", f"{base}/admin/index/{path.name}/complete"
                                 f"?upload_id={upload_id}", token, b""),
    )
    print(f"  {path.name}: assembled in {time.time() - t0:.0f}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True, type=Path)
    ap.add_argument("--url", required=True, help="AppSail base URL")
    ap.add_argument("--token", required=True, help="INDEX_PUSH_TOKEN")
    args = ap.parse_args()

    base = args.url.rstrip("/")

    # manifest.json goes LAST, deliberately. ensure_index() decides whether
    # to download by comparing the manifest's fingerprint, so writing it
    # first would advertise an index whose vectors are still uploading —
    # and a container restarting in that window would fetch a torn one.
    order = ["vectors.f16.npy", "chunks.jsonl.gz", "vocabulary.json", "manifest.json"]
    missing = [n for n in order if not (args.dist / n).exists()]
    if missing:
        raise SystemExit(f"missing from {args.dist}: {', '.join(missing)}")

    t0 = time.time()
    for name in order:
        path = args.dist / name
        if path.stat().st_size <= SINGLE_SHOT_MAX:
            push_small(path, base, args.token)
        else:
            push_multipart(path, base, args.token)

    print(f"pushed in {time.time() - t0:.0f}s")
    print("the container picks this up on its next restart; nothing is live yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
