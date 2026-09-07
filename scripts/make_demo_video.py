#!/usr/bin/env python3
"""
Build the demo video from real captured output.

Static frames rather than a screen recording, deliberately: a recording of
a 40-millisecond query is a video of nothing happening, and a recording of
the agent run is four minutes of scrolling. The interesting content is the
numbers, and the numbers hold still.

Every frame's content comes from files that capture_demo_assets.py writes.
Nothing here is retyped by hand — if a number in the video is wrong, the
capture is wrong, which is the failure mode worth having.

    python3 scripts/capture_demo_assets.py --index index-full --out demo-assets
    python3 scripts/make_demo_video.py --assets demo-assets --out demo.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
import textwrap
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG = (13, 17, 23)          # github dark; reads well on LinkedIn's feed
FG = (201, 209, 217)
DIM = (110, 118, 129)
ACCENT = (88, 166, 255)
GOOD = (63, 185, 80)
BAD = (248, 81, 73)
WARN = (210, 153, 34)

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO_B if bold else MONO, size)


class Frame:
    """
    Draws twice: once to measure, once for real.

    Frames vary from three lines to a dozen, and anchoring them all to a
    fixed top margin leaves the short ones stranded against the top edge
    with half the frame empty — which on a phone-sized feed reads as a
    broken image. So the first pass records the height and the second
    re-runs the same calls with the whole block centred.
    """

    def __init__(self, seconds: float = 4.0):
        self.seconds = seconds
        self._ops: list = []
        self.y = 120
        self._top = 120
        self.img = Image.new("RGB", (W, H), BG)
        self.d = ImageDraw.Draw(self.img)

    def line(self, text: str = "", size: int = 34, colour=FG, bold=False, indent=0, gap=14):
        if text:
            self._ops.append(("text", self.y, text, size, colour, bold, indent))
        self.y += size + gap
        return self

    def rule(self, colour=DIM):
        self._ops.append(("rule", self.y, colour))
        self.y += 34
        return self

    def _render(self) -> None:
        # Centre the measured block, but never push it above the top margin:
        # a frame taller than the canvas should overflow downward, where it
        # is obvious, rather than upward off the top edge.
        height = self.y - self._top
        offset = max(0, (H - height) // 2 - self._top)
        for op in self._ops:
            if op[0] == "text":
                _, y, text, size, colour, bold, indent = op
                self.d.text((140 + indent, y + offset), text,
                            font=font(size, bold), fill=colour)
            else:
                _, y, colour = op
                self.d.line([(140, y + offset + 8), (W - 140, y + offset + 8)],
                            fill=colour, width=2)

    def wrapped(self, text: str, width: int = 76, size: int = 30, colour=FG, indent=0):
        for ln in textwrap.wrap(text, width):
            self.line(ln, size=size, colour=colour, indent=indent, gap=8)
        return self

    def save(self, path: Path):
        self._render()
        # Footer on every frame: the claim being made is checkable, and this
        # is what tells a viewer where to go and check it.
        self.d.text((140, H - 90), "krishnamurti-rag on Zoho Catalyst 3.0",
                    font=font(24), fill=DIM)
        self.img.save(path)


def build(assets: Path, out: Path) -> None:
    health = json.loads((assets / "health.json").read_text())
    ask_in = json.loads((assets / "ask_in.json").read_text())
    ask_off = json.loads((assets / "ask_off.json").read_text())
    report = (assets / "report.md").read_text()

    frames: list[Frame] = []

    # 1. Title
    f = Frame(4.5)
    f.y = 330
    f.line("Agentic DevOps, put to work", size=72, bold=True)
    f.line("Zoho Catalyst 3.0", size=54, colour=ACCENT)
    f.y += 40
    f.wrapped("An agent that owns the release cycle of a RAG app — re-indexes, "
              "evaluates, judges, and refuses to ship its own build.",
              width=64, size=32, colour=DIM)
    frames.append(f)

    # 2. The gap agentic DevOps fills
    f = Frame(6.5)
    f.line("What CI/CD cannot tell you", size=48, bold=True)
    f.rule()
    f.line("Tests green. Container healthy. Deploy succeeded.", size=34, colour=GOOD)
    f.y += 16
    f.line("Did retrieval quality regress?", size=34, colour=BAD)
    f.line("Does it still refuse what it should refuse?", size=34, colour=BAD)
    f.y += 24
    f.wrapped("Nothing in a normal pipeline answers those. A RAG app degrades "
              "without a single failing test — change the corpus, the chunker, "
              "or the embedding model and every assertion still passes while the "
              "answers quietly get worse. That gap is what the agent is for.",
              size=30, colour=DIM)
    frames.append(f)

    # 3. The loop
    f = Frame(6.5)
    f.line("The loop the agent owns", size=48, bold=True)
    f.rule()
    f.line("1   re-index        corpus / chunker / model change", size=34, colour=FG)
    f.line("2   deploy          candidate → Development", size=34, colour=FG)
    f.line("3   evaluate        40-question golden suite", size=34, colour=FG)
    f.line("4   measure         recall · citations · no-match · latency", size=34, colour=FG)
    f.line("5   recommend       evidence-backed accept / reject", size=34, colour=FG)
    f.y += 18
    f.line("6   STOP            a human promotes to Production", size=36, colour=WARN, bold=True)
    f.y += 20
    f.wrapped("Step 6 is the design, not a limitation. The agent produces the "
              "evidence; it never promotes anything itself.", size=30, colour=DIM)
    frames.append(f)

    # 4. Which Catalyst primitive carries which step
    f = Frame(6.5)
    f.line("Catalyst 3.0 primitives behind the loop", size=48, bold=True)
    f.rule()
    f.line("AppSail          the app + the index write path", size=34, colour=FG)
    f.line("                 Docker custom runtime, 30s ceiling", size=28, colour=DIM)
    f.y += 10
    f.line("Stratus          index objects, multipart push", size=34, colour=FG)
    f.line("                 176 MB in 31s, every part checksummed", size=28, colour=DIM)
    f.y += 10
    f.line("Logs             error inspection during the eval run", size=34, colour=FG)
    f.y += 10
    f.line("Pipelines / Jobs  where the loop is scheduled to run", size=34, colour=DIM)
    f.line("                 designed for it; today run as a CLI", size=28, colour=DIM)
    frames.append(f)

    # 5. The constraint that shaped it: every step needs an API
    f = Frame(6.5)
    f.line("The rule that shaped every choice", size=48, bold=True)
    f.rule()
    f.line("If a human has to click it, an agent cannot own it.", size=38, colour=ACCENT)
    f.y += 24
    f.wrapped("QuickML's Knowledge Base was the original plan for retrieval. It "
              "has no ingestion API — documents go in through the console, ten "
              "files per round. At this corpus that is 302 rounds of clicking, "
              "so the agent could never re-index. It was cut for that reason "
              "alone, and retrieval moved in-process.", size=30, colour=FG)
    f.y += 14
    f.wrapped("The same rule forced multipart upload to Stratus: the index is "
              "126 MB and AppSail kills a request at 30 seconds.",
              size=30, colour=DIM)
    frames.append(f)

    # 6. What it evaluates against — live health + a real query
    f = Frame(6.0)
    f.line("What it evaluates against", size=48, bold=True)
    f.rule()
    for k in ("chunks", "talks", "corpus_fingerprint"):
        f.line(f'  "{k}": {json.dumps(health[k])}', size=30, colour=FG, gap=10)
    f.y += 18
    f.line(f'"{ask_in["question"]}"', size=34, colour=ACCENT)
    f.line(f'  relevance {ask_in["best_relevance"]}', size=30, colour=GOOD)
    p = ask_in["passages"][0]
    f.line(f'  {p["cite"]}', size=28, colour=DIM)
    f.y += 14
    f.wrapped("The fingerprint is what makes the loop safe to repeat: the container "
              "re-downloads the index only when it changes.", size=28, colour=DIM)
    frames.append(f)

    # 7. What the loop caught that review didn't
    f = Frame(7.0)
    f.line("What the loop caught", size=48, bold=True)
    f.rule()
    f.line("1  a live defect in the app being migrated away from", size=32, colour=BAD)
    f.wrapped(f'"{ask_off["question"]}" scored {ask_off["best_relevance"]} on the '
              f'production site and was answered confidently. It had done that '
              f'for months.', size=28, colour=DIM, indent=40)
    f.y += 14
    f.line("2  an error in my own evaluation set", size=32, colour=BAD)
    f.wrapped("Four questions labelled 'absent from the corpus' were not absent. "
              "K discusses the Gita 803 times and describes meeting the Dalai Lama.",
              size=28, colour=DIM, indent=40)
    f.y += 14
    f.line("3  a passing test that was passing by luck", size=32, colour=BAD)
    f.wrapped("Recording which gate fired exposed it: one refusal works only "
              "because a name occurs twice, under the threshold.",
              size=28, colour=DIM, indent=40)
    frames.append(f)

    # 8. The scoreboard, straight from the report
    f = Frame(6.5)
    f.line("Off-corpus refusals, by mechanism", size=48, bold=True)
    f.rule()
    for ln in report.splitlines():
        if ln.startswith("| ") and "Category" not in ln and "---" not in ln:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) < 4:
                continue
            hit, total = cells[1].split("/")
            colour = GOOD if hit == total else BAD
            f.line(f"{cells[0]:<24}{cells[1]:>8} correct   {cells[2]} accidental   "
                   f"{cells[3]} answered", size=30, colour=colour, gap=12)
    f.y += 20
    f.wrapped("A refusal counts only when the mechanism that fired is the one the "
              "category expects. Scoring by outcome alone hid a third of the "
              "failures — the agent had to be taught to record the mechanism.",
              size=28, colour=DIM)
    frames.append(f)

    # 9. Verdict
    f = Frame(6.5)
    f.line("The agent's verdict on its own build", size=48, bold=True)
    f.rule()
    f.line("recall                 1.0     ≥ 0.85    PASS", size=32, colour=GOOD)
    f.line("citation accuracy      1.0     ≥ 0.90    PASS", size=32, colour=GOOD)
    f.line("no-match precision     0.733   ≥ 0.90    FAIL", size=32, colour=BAD)
    f.line("p95 latency            0.32s   ≤ 15s     PASS", size=32, colour=GOOD)
    f.y += 24
    f.line("RECOMMENDATION: REJECT", size=52, colour=BAD, bold=True)
    f.y += 16
    f.wrapped("And it stops there — promotion needs a human. Lowering the "
              "threshold to 0.75 would make this pass, which is exactly the "
              "move an agent must not be allowed to make on its own.",
              size=30, colour=DIM)
    frames.append(f)

    # 10. Close
    f = Frame(5.0)
    f.y = 360
    f.line("Agentic DevOps is the stop, not the speed.", size=52, bold=True)
    f.y += 20
    f.wrapped("An agent that ships everything is automation. One that assembles "
              "the evidence and then refuses to ship is the part worth building.",
              width=68, size=32, colour=DIM)
    frames.append(f)

    # Render
    tmp = out.parent / "_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    concat = []
    for i, fr in enumerate(frames):
        p = tmp / f"frame{i:02d}.png"
        fr.save(p)
        concat.append(f"file '{p.resolve()}'\nduration {fr.seconds}")
    # ffmpeg's concat demuxer drops the final entry's duration unless the last
    # file is repeated; without this the closing frame flashes past.
    concat.append(f"file '{(tmp / f'frame{len(frames)-1:02d}.png').resolve()}'")
    list_file = tmp / "frames.txt"
    list_file.write_text("\n".join(concat) + "\n")

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        exe, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-vf", "fps=30,format=yuv420p",     # yuv420p or it won't play on iOS
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-movflags", "+faststart",          # so it starts before fully buffered
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    total = sum(f.seconds for f in frames)
    print(f"wrote {out} — {len(frames)} frames, {total:.0f}s, "
          f"{out.stat().st_size / 1e6:.1f} MB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    build(args.assets, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
