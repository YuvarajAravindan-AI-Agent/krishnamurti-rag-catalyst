# Krishnamurti RAG — Netcup to Catalyst 3.0 migration

A retrieval-augmented Q&A app over ~3,000 J. Krishnamurti public talk
transcripts (source: [kfoundation.org](https://kfoundation.org)), migrated
from a self-hosted Netcup VPS (FastAPI + Ollama + Chroma) to
[Zoho Catalyst 3.0](https://catalyst.zoho.com/blog/meet-catalyst-3.0.html) —
built specifically to demo **agentic DevOps**, Catalyst 3.0's core pitch.

The RAG app is the substrate. The actual point is the **release-quality
agent** in [`agent/release_quality_agent.py`](agent/release_quality_agent.py):
on any corpus/prompt/model change it re-indexes, runs a golden evaluation
suite, measures retrieval quality end to end, and produces an
evidence-backed accept/reject recommendation — then **stops and waits for a
human to click promote**. No autonomous production promotion, ever.

## Architecture

```
Browser  →  AppSail (FastAPI, one origin)
                →  QuickML RAG / Knowledge Base   (retrieval)
                →  QuickML managed LLM             (synthesis)
Job Scheduling + Pipelines + Logs for the agent loop
```

Caddy + Ollama + Chroma are gone entirely — Catalyst's AppSail handles TLS,
domain mapping, and hosting; QuickML replaces the local embedding/retrieval
stack. See [`krishnamurti-rag-catalyst-migration-plan.md`](docs/migration-plan.md)
for the full execution plan this was built from.

## Layout

- `appsail/` — the FastAPI app + static query UI, deployed as a Docker Image
  AppSail service
- `agent/` — the release-quality agent (non-interactive CLI, meant to run via
  Catalyst Pipelines/Job Scheduling)
- `eval/golden_set.json` — 25 in-corpus + 15 off-corpus questions (including
  adjacent-but-wrong traps: named philosophers/teachers who aren't K) used
  by both the retrieval-threshold calibration and the agent's evaluation pass
- `scripts/` — one-off migration scripts (transcript splitting, demo subset
  selection)

## Status

- [x] Source data frozen and exported from the Netcup box
- [x] Golden evaluation set expanded (8+8 → 25+15)
- [x] Catalyst project created (`krishnamurti-rag-catalyst`, DC: in)
- [x] 3,014 transcripts split into per-talk documents; a 62-talk demo subset
      staged for QuickML Knowledge Base ingestion
- [ ] QuickML RAG configured against the ingested corpus
- [ ] Retrieval threshold recalibrated for the new embedding model
- [ ] AppSail deployment live
- [ ] Shadow test vs the Netcup app on the golden set
- [ ] Release-quality agent run end-to-end, including a staged regression
- [ ] Netcup box decommissioned after a 30-day rollback window

## Why not lift-and-shift Ollama + Chroma?

AppSail's request limit is 30s; the original Ollama-based synthesis measured
up to 47s to first token on hard CPU cases. QuickML's managed LLM serving
avoids that live-timeout risk entirely — this is a genuine architecture
change, not a rehost.

## Live app

TBD — will be linked here once the AppSail deployment passes shadow testing.
Netcup original (rollback target during transition): https://jk.ai-agentic-enterprises.com
