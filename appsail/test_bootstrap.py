"""
Bootstrap test: does the container survive having no index?

This is not a formality. The first deploy starts with an empty bucket, and
the only route that can fill it lives on the container itself, so a startup
that exits on a missing index can never be repaired by the agent — it has
to be repaired by hand, which is the manual step this whole design exists
to remove.

    python3 appsail/test_bootstrap.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["INDEX_DIR"] = tempfile.mkdtemp(prefix="empty-index-")
os.environ["INDEX_PUSH_TOKEN"] = "test-token"
os.environ["INDEX_BUCKET_URL"] = "https://127.0.0.1:9"  # guaranteed unreachable

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: got {got}, want {want}")
    if not ok:
        failures.append(label)


with TestClient(server.app) as c:
    print("no index available:")
    h = c.get("/health").json()
    check("health responds", h.get("degraded"), True)
    check("ask refuses", c.post("/api/ask", json={"question": "what is fear?"}).status_code, 503)
    check("wrong token rejected",
          c.put("/admin/index/manifest.json", content=b"{}",
                headers={"x-index-token": "wrong"}).status_code, 403)
    check("unknown key rejected",
          c.put("/admin/index/evil.sh", content=b"x",
                headers={"x-index-token": "test-token"}).status_code, 400)
    check("empty body rejected",
          c.put("/admin/index/manifest.json", content=b"",
                headers={"x-index-token": "test-token"}).status_code, 400)
    # Locally there are no Catalyst credential headers, so the SDK must fail
    # loudly rather than silently pretending to have written anything.
    r = c.put("/admin/index/manifest.json", content=b"{}",
              headers={"x-index-token": "test-token"})
    check("valid push fails without Catalyst headers (expected off-platform)",
          r.status_code, 500)
    print(f"    -> {str(r.json().get('detail'))[:120]}")

print("FAILURES:", failures or "none")
sys.exit(1 if failures else 0)
