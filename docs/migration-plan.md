# Krishnamurti RAG → Catalyst 3.0 migration + agentic DevOps demo — execution plan

Written to be picked up cold in a new session with zero prior context. Source
brief: `~/Documents/Codex/2026-09-06/i-want-you-to-do-three/outputs/third-part-rag-catalyst-migration-brief.pdf`
(4 pages, prepared 2026-09-06 — read it first, this doc extends it with exact
commands and this project's own hard-won Catalyst lessons).

---

## 0. The actual goal — read this before doing anything

Yuvaraj does **not** want "move the RAG app to Catalyst" as the deliverable.
He wants a **demo of agentic DevOps behavior**, because Catalyst 3.0's whole
pitch is agentic DevOps (Agent Skills, MCP, non-interactive CLI, Pipelines,
Job Scheduling) — a generic "look, an agent answers questions" demo doesn't
showcase that. The RAG migration is the **substrate**; the star of the demo
is an agent that manages the migration's re-indexing/evaluation/promotion
cycle autonomously, with a human approval gate before production.

This is exactly **"RAG reliability and release-quality agent"** from the
brief (§3), which is also **use case #15** from an earlier session's list of
16 possible Catalyst 3.0 agentic DevOps use cases (see
`ai-agentic-enterprises-site` memory / earlier LinkedIn-post-audit session —
not reproduced here, the short version is: this was independently identified
twice as the best fit).

**Do not build a plain migration and call it done.** The deliverable is:
1. The RAG app running on Catalyst (QuickML-based, not lift-and-shift).
2. An agent — triggered by a corpus/embedding/prompt/model change — that
   re-indexes, runs a golden evaluation suite, and produces an
   evidence-backed accept/reject recommendation, with a human clicking
   "promote to production."
3. A recording/demo of that agent loop actually running, since that's the
   thing worth putting on LinkedIn — not the RAG app itself, which was
   already posted once.

---

## 1. What's live today (verified, don't re-verify from scratch)

- **URL**: https://jk.ai-agentic-enterprises.com — confirmed working via
  direct WebSocket test in an earlier session (not just curl-to-homepage).
- **Host**: Netcup RS 1000 G12, SSH alias `jk-box` (also `netcup-jk`),
  `159.195.108.208`, user `yuvaraj`, key `~/.ssh/id_ed25519_netcup_jk`.
- **App dir**: `~/krishnamurti-rag/` on that box. Key files: `server.py`
  (362 lines, FastAPI + WebSocket `/ws`), `ingest.py`, `chunk.py`, `index.py`,
  `calibrate.py`, `fetch_transcripts.py`, `ask.py`.
- **Data**: `data/chroma` (1.3 GB), `data/chunks.json` (162 MB),
  `data/transcripts.json` (105 MB), `data/corpus.json`, plus small Wikiquote
  files. **163,829 chunks** from **3,014 transcripts**.
- **Model stack**: Ollama `qwen3:1.7b` (chat) + `all-minilm` (embeddings,
  45 MB). `qwen3:4b` also pulled but unused by default.
- **Retrieval guardrail**: `MIN_RELEVANCE = 0.5` in `server.py`, calibrated
  empirically — in-corpus questions score 0.68–0.81, off-corpus 0.17–0.36.
  **This exact threshold is meaningless on a different embedding model** —
  it must be recalibrated from scratch on Catalyst (see §4 step 5, and
  `calibrate.py` which already exists for this purpose).
- **systemd services on jk-box**: `caddy`, `krishnamurti.service`,
  `ollama.service`. Caddy on jk-box itself terminates TLS for
  `jk.ai-agentic-enterprises.com` — this is a **separate box** from
  `contabo-tally` (169.58.69.167), which hosts unrelated projects. Don't
  confuse the two Caddyfiles.
- **Protocol**: client opens `wss://…/ws`, sends
  `{"question": "...", "include_early": bool}`, receives `{"type":
  "passages", ...}` then `{"type": "synthesis_start"}` then streamed tokens.
  System prompt lives in `server.py` line 107 (`SYSTEM_PROMPT`).

## 2. Target architecture (from the brief, §2)

```
Browser  →  AppSail (custom Docker FastAPI, UI + API, one origin)
                  →  QuickML RAG / Document Search  (retrieval)
                  →  QuickML managed LLM             (synthesis)
                  →  Stratus                          (backups, manifests)
Job Scheduling + Pipelines + Logs/Alerts/Metrics for the DevOps agent loop
```

Caddy is removed entirely — Catalyst provides TLS + domain mapping directly
on AppSail. **Do not lift-and-shift Ollama+Chroma into AppSail** — the brief
is explicit about this and it's correct: AppSail's ordinary request limit is
30 s, and the original post already measured up to 47 s to first token on
hard CPU cases. That's a live-timeout risk, not a hypothetical one.

## 3. Operating lessons from this session's Catalyst work (invoice-ocr-pipeline) — apply these here too

These cost real debugging time on a *different* Catalyst project this
session. They generalize to any Catalyst 3.0 work, including this one:

1. **Catalyst CLI is already authenticated** on this machine (`catalyst`
   installed at `~/.npm-global/bin/catalyst`, `catalyst project:list` works
   without login). Org: `yuvarajaravindan` (`60086011005`), DC: `in`.
   Existing projects: `claude-commerce-demo`, `invoice-ocr-pipeline`,
   `Project-Rainfall`. **Create a new project** for this (e.g.
   `krishnamurti-rag-catalyst`) rather than reusing one of these.
2. **Docker Image AppSail deploys need the `localhost/` prefix on the
   image tag**, or `catalyst deploy appsail` fails with "no such image":
   `docker tag myimage:latest localhost/myimage:latest`, then
   `--source docker://localhost/myimage:latest`.
3. **Environment variables for Docker Image (custom-runtime) AppSail
   services cannot be set via CLI or `app-config.json` at all** —
   `app-config.json` is only generated for Catalyst-managed runtimes.
   The **only** way is the console's AppSail → Configuration →
   Environment Variables tab. Budget for this as a manual step every
   time a new secret (e.g. a QuickML API key, if one is needed) is
   introduced.
4. **Trust nothing about undocumented response shapes — verify against a
   live call before writing the "final" adapter code.** On
   invoice-ocr-pipeline, Zia OCR's response for a PDF omitted the
   `confidence` key entirely (present for images), which the docs never
   mentioned and which crashed the worker in production before it was
   caught by testing with a real PDF, not just a real image. **Do the
   same defensive testing for QuickML's RAG/Document Search response
   shape before building the re-indexing agent around it** — call it
   directly first (via `catalyst serve` or a scratch script), print the
   raw response, and only then write code that assumes a particular
   shape.
5. **Data Store DateTime columns want `"YYYY-MM-DD HH:MM:SS"`**, not
   `datetime.isoformat()` (which uses `T` and microseconds) — irrelevant
   to QuickML directly, but relevant if the release-quality agent logs
   evaluation runs into a Catalyst Data Store table.
6. **AppSail's outbound network rejects raw Postgres (port 5432) and, in
   this session's testing, also rejected an HTTPS-proxied Postgres from
   a different box** — confirmed via a live gateway-level 500 in both
   cases. If the release-quality agent needs to persist evaluation
   history anywhere other than Catalyst Data Store/Stratus, do not
   assume an external database will be reachable from AppSail; test it
   directly and early, exactly as this plan's own §4 step 3 suggests
   testing QuickML.
7. **A one-page manual test UI on the AppSail service (a static HTML
   form) is worth building early**, not as an afterthought — it's what
   turned "trust the JSON response" into "watch it actually work,"
   caught two real bugs, and is what a LinkedIn visitor needs to try
   the thing themselves without curl. Build the query UI on Catalyst
   before the agent loop, exactly as the brief's own migration sequence
   already implies (§2, "Recreate the UX" is step 6, before "Shadow
   test" step 7).
8. **Browser automation for anything requiring a live Zoho console
   session must go through the user's actual logged-in Chrome**, not a
   sandboxed preview browser — the sandbox has no access to the user's
   Zoho session cookies. Use whatever the "claude-in-chrome"-equivalent
   tool is in the next session, and expect coordinate-based UI
   automation (console SPA) to be flaky — verify state with
   `get_page_text`/ZCQL queries after every destructive action, not
   just screenshots.

## 4. Migration sequence (from the brief §2, with concrete next steps added)

1. **Freeze and export** — SSH to `jk-box`, tar up `~/krishnamurti-rag/data/`
   (transcripts, corpus, chunks, chroma snapshot), note `EMBED_MODEL`,
   `CHAT_MODEL`, `MIN_RELEVANCE` from `server.py`, and pull `calibrate.py`'s
   evaluation question set (check if one exists in the repo/history — if
   not, write 10–15 in-corpus + 10–15 off-corpus questions before
   proceeding, since §4 step 5 and the whole release-quality agent depend
   on having a golden set).
2. **Stage source documents** — `data/transcripts.json` (105 MB) needs to
   become individual documents QuickML's Knowledge Base can ingest
   (PDF/DOCX/TXT, ≤500 KB each per the brief). Write a small script to
   split `transcripts.json` into per-talk `.txt` files with title/date
   embedded in the content (see step 4). Check WorkDrive bulk-upload
   limits before assuming the naive per-file approach scales to 3,014
   files without batching/rate-limiting.
3. **Rebuild retrieval** — create the QuickML RAG config via console (no
   CLI path is likely to exist, per §3.2 above's general pattern — verify
   this rather than assume). **Do not attempt to import the Chroma vectors
   directly** — the brief is explicit and correct that they're not
   portable to QuickML's index.
4. **Preserve citations** — every per-talk document must carry title, date,
   and the original `kfoundation.org` URL, either inline or in a parallel
   manifest QuickML can surface. Check `fetch_transcripts.py` for how the
   original URLs were captured.
5. **Recalibrate guardrails** — run `calibrate.py`'s methodology (or its
   logic ported to call QuickML instead of local Ollama) against the new
   embedding distribution. **The 0.5 threshold does not transfer.**
6. **Recreate the UX** — same query box / passages-then-summary UX as
   today, built as a static HTML page + FastAPI on AppSail (see §3.7
   above). Keep the "passages first, summary labelled as model-written"
   trust pattern — that's the actual product, not an implementation
   detail.
7. **Shadow test** — run the golden question set against both jk-box (live)
   and the Catalyst candidate side by side; compare recall, citation
   accuracy, unsupported-claims rate, no-match precision, latency.
8. **Promote and cut over** — Development → review evidence → manual
   promotion to Production → domain mapping → keep jk-box live as
   rollback until confidence is high.

## 5. The agent to build (the actual demo)

**RAG reliability and release-quality agent.** Trigger: any corpus,
embedding, prompt, or model change. Behavior:

1. Ingest/validate the changed source documents into QuickML.
2. Deploy the candidate to the Development environment.
3. Run the golden evaluation suite from §4 step 1/5 against it.
4. Measure: retrieval recall, citation correctness, unsupported-claims
   rate, no-match precision, latency (time-to-passages and
   time-to-full-answer, separately — per the brief's own latency risk
   note in §3).
5. Inspect Catalyst Logs for errors during the run.
6. Produce a written, evidence-backed accept/reject recommendation
   (pass/fail against the acceptance checklist in §6 below).
7. **Stop and wait for human approval** before promoting to Production —
   this is a deliberate, demoable safety boundary, not a limitation.

Building blocks per the brief (§3): Agent Skills + MCP for platform-aware
changes, non-interactive CLI + Pipelines for delivery, Job Scheduling for
corpus refresh, QuickML for the RAG endpoints being evaluated, Logs/Alerts/
Metrics for the evidence the agent's report is built from.

**Concretely, this is likely a Python script (or Catalyst Function) that**:
- calls the non-interactive `catalyst` CLI or MCP tools to deploy,
- calls the QuickML RAG endpoint directly with the golden question set,
- scores the responses (start simple: keyword/URL-match for citations,
  a similarity threshold for recall — don't over-engineer this before the
  simple version is proven to work end-to-end),
- writes a report (Markdown or a Data Store row) and stops.

## 6. Acceptance checklist (from the brief, §3 — keep as-is)

- [ ] All 3,014 transcripts imported and accounted for.
- [ ] Citation URLs and dates match the original corpus.
- [ ] No-match tests pass and citations remain correct.
- [ ] Latency targets are met and jk-box rollback remains available.
- [ ] (Added) The release-quality agent runs end-to-end at least once on a
      real corpus change and produces a report a human actually reads
      before promoting.

## 7. Decisions (Yuvaraj delegated these — "take your own decision" — settled 2026-09-06)

1. **Region: `in` (same DC/org as invoice-ocr-pipeline, org `yuvarajaravindan`,
   60086011005).** Reasoning: two `WebSearch` passes turned up no evidence
   Catalyst's underlying compute/subscription cost actually differs by DC —
   pricing is just displayed/billed in the DC's local currency (INR for
   `in`, USD for `us`, etc.), not structurally discounted anywhere. Given
   that, cost-effectiveness for an India-based payer favors **avoiding
   forex conversion/markup** by staying in INR, plus reusing the existing
   org's free-tier allocation instead of a second signup. **Trade-off
   accepted**: the brief's §7 note stands — `in` DC lacks built-in
   Automation Testing, so the release-quality agent's evaluation loop runs
   as a plain script invoked via CLI/Pipelines, not Catalyst's built-in
   test runner. That was already the simpler, more demoable path anyway
   (§5 already specs it as "a Python script/Catalyst Function," not a test
   suite), so this costs nothing. Create a **new project**
   (`krishnamurti-rag-catalyst`) under the same org, per §3.1.
2. **Golden question set: check jk-box first, write fresh if absent.**
   `calibrate.py` exists on jk-box (§1) but whether it embeds/reads a fixed
   question set vs. taking ad-hoc input wasn't confirmed in an earlier
   session — first action in §4 step 1 is `ssh jk-box` and read
   `calibrate.py` plus any adjacent `*.json`/`*.csv` it references. If none
   exists, write ~24–30 fresh: half in-corpus (spread across recurring
   K-speaks themes — fear, authority, self-knowledge, relationship,
   awareness — not just one topic repeated), half off-corpus including a
   few *adjacent-but-wrong* traps (e.g. a named-philosopher question that
   sounds on-topic but isn't K's material) to stress the no-match guardrail
   harder than a purely random off-corpus set would.
3. **Demo framing: LinkedIn, and yes — stage a deliberate regression.**
   Matches the pattern that already worked for the invoice-ocr-pipeline
   demo (the judge *catching* a wrong vendor name was the memorable part,
   not the happy path). Concretely: after the first clean promotion, make
   a second corpus/prompt change known to hurt citation accuracy or
   recall (e.g. shrink chunk overlap, or drop the citation-URL field from
   a subset of documents), run the agent, and record it producing a
   reject recommendation with evidence — that's the clip worth posting.
4. **Netcup box: keep running for a hard 30-day rollback window after the
   Catalyst version passes the §4 step 7 shadow test**, not indefinitely.
   It's billed monthly (~€12.92/mo per prior Netcup context) with no
   reason to keep paying for it once Catalyst is proven equivalent or
   better on the golden set — 30 days is enough buffer to catch anything
   the shadow test missed (real user traffic patterns, edge-case
   questions) without open-ended cost. Set a calendar reminder / note the
   cutover date once the shadow test passes; decommission jk-box
   (stop `krishnamurti.service`/`ollama.service`/`caddy`'s route for it,
   don't touch other things on that box if any) after the window closes
   with no rollback need.

## 8. Sources

- Brief: `~/Documents/Codex/2026-09-06/i-want-you-to-do-three/outputs/third-part-rag-catalyst-migration-brief.pdf`
- Live app: https://jk.ai-agentic-enterprises.com
- Catalyst 3.0: https://catalyst.zoho.com/blog/meet-catalyst-3.0.html
- QuickML RAG: https://docs.catalyst.zoho.com/en/quickml/help/generative-ai/rag/
- AppSail limits: https://docs.catalyst.zoho.com/en/serverless/help/appsail/appsail-basics/
- This session's invoice-ocr-pipeline work (for the operating lessons in
  §3): `~/Projects/invoice-ocr-pipeline/`, live at
  https://api-50045555479.development.catalystappsail.in/
