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

→ On any corpus, prompt, or model change, it re-indexes
→ Runs a 40-question golden evaluation suite (in-corpus + off-corpus,
  including questions that name other teachers and sound entirely on-topic)
→ Measures retrieval recall, citation accuracy, unsupported-claims rate,
  no-match precision, and latency
→ Produces a written accept/reject recommendation with evidence
→ **Stops. Waits for a human to click promote.**

Two things it found that I didn't expect.

First, a live defect in the app I was migrating *away* from. Ask the running
production site "what did Osho teach about meditation?" and it scores 0.618
against its relevance threshold and answers confidently. The question is
genuinely about meditation, so cosine distance has no way to reject it. It
had been doing that for months.

Second — and this is the part I keep thinking about — it caught an error in
my own evaluation set. I'd labelled seven named-teacher questions as traps
whose material was "genuinely absent" from the corpus. Four of them weren't.
Krishnamurti discusses the Bhagavad Gita 803 times, refers to Rajneesh, and
describes meeting the Dalai Lama. On Ramana Maharshi, in Gstaad in 1962, he
says: "I don't know these birds… Why should I know them?"

Those questions are still unanswerable — the archive holds his refusal of
the subject, not the teaching — but that's a harder problem than the one I
thought I was solving, and my headline number went from 7/7 to 3/3 plus a
documented open failure mode.

Which is the actual argument for building the judge. A demo tuned until it
passes tells you nothing. One that can tell you your own scoring was wrong
is worth having.

🔗 GitHub: [link]
🔗 Live app: [link]
📝 Full writeup: [Medium link]
🎙️ Podcast breakdown: [link]

#ZohoCatalyst #AgenticDevOps #RAG #AIEngineering
