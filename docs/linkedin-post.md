# LinkedIn post draft

**Title:** Jiddu Krishnamurti RAG — Netcup to Catalyst 3.0 migration project

---

I migrated a RAG app answering questions over ~3,000 J. Krishnamurti public
talk transcripts off a self-managed Netcup VPS (FastAPI + Ollama + Chroma)
onto Zoho Catalyst 3.0.

But the migration isn't the interesting part. Catalyst 3.0's pitch is
**agentic DevOps** — Agent Skills, MCP, non-interactive CLI, Pipelines, Job
Scheduling — and a RAG app answering questions doesn't showcase any of that.
So the actual deliverable is an agent that manages the migration's own
release cycle:

→ On any corpus, prompt, or model change, it re-indexes the knowledge base
→ Runs a 40-question golden evaluation suite (in-corpus + adversarial
  off-corpus questions, including named-philosopher traps that sound
  on-topic but aren't K's material)
→ Measures retrieval recall, citation accuracy, unsupported-claims rate,
  no-match precision, and latency
→ Produces a written accept/reject recommendation with evidence
→ **Stops. Waits for a human to click promote.**

To make the point concrete, I staged a deliberate regression after the
first clean promotion — shrunk chunk overlap enough to hurt citation
accuracy — and recorded the agent catching it and recommending reject, with
the evidence to back it up.

That's the clip worth watching: not the happy path, the judge catching the
regression.

🔗 GitHub: [link]
🔗 Live app: [link]
📝 Full writeup: [Medium link]
🎙️ Podcast breakdown: [link]

#ZohoCatalyst #AgenticDevOps #RAG #AIEngineering
