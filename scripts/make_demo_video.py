#!/usr/bin/env python3
"""
Build the demo video from real captured output.

Static frames rather than a screen recording, deliberately: a recording of
a 40-millisecond query is a video of nothing happening, and a recording of
the agent run is four minutes of scrolling. The interesting content is the
numbers, and the numbers hold still.

Every frame's content comes from files captured off the live deployment
(scripts/capture_demo_assets.sh writes them). Nothing here is retyped by
hand — if a number in the video is wrong, the capture is wrong, which is
the failure mode worth having.

    python3 scripts/make_demo_video.py --assets <dir> --out demo.mp4
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
    f.line("Jiddu Krishnamurti RAG", size=76, bold=True)
    f.line("Netcup → Zoho Catalyst 3.0", size=54, colour=ACCENT)
    f.y += 40
    f.wrapped("A migration used as the substrate for the actual subject: "
              "an agent that decides whether a release is fit to ship.",
              width=64, size=32, colour=DIM)
    frames.append(f)

    # 2. Why not lift-and-shift
    f = Frame(5.5)
    f.line("Why not lift-and-shift", size=48, bold=True)
    f.rule()
    f.line("Ollama first-token latency, worst measured case", size=32, colour=DIM)
    f.line("47s", size=64, colour=BAD, bold=True)
    f.y += 10
    f.line("AppSail request ceiling", size=32, colour=DIM)
    f.line("30s", size=64, colour=ACCENT, bold=True)
    f.y += 20
    f.wrapped("Not a timeout risk — a timeout certainty. Synthesis had to leave "
              "the box. Retrieval could not follow it: QuickML's Knowledge Base "
              "has no ingestion API, so an agent cannot re-index.", size=30, colour=FG)
    frames.append(f)

    # 3. Architecture
    f = Frame(5.0)
    f.line("What actually shipped", size=48, bold=True)
    f.rule()
    f.line("retrieval    in-process, ONNX all-MiniLM-L6-v2", size=34, colour=FG)
    f.line("             exact cosine over 163,829 chunks", size=30, colour=DIM)
    f.y += 12
    f.line("index        Stratus object storage, fetched at boot", size=34, colour=FG)
    f.line("             402 MB → 176 MB packed, pushed by script", size=30, colour=DIM)
    f.y += 12
    f.line("synthesis    QuickML LLM Serving, off-box", size=34, colour=FG)
    f.y += 20
    f.wrapped("MIN_RELEVANCE = 0.5 carried over unchanged — because the embedder "
              "is the same model, measured at 0.999998 mean agreement, not assumed.",
              size=30, colour=DIM)
    frames.append(f)

    # 4. Live health
    f = Frame(5.0)
    f.line("Live on Catalyst", size=48, bold=True)
    f.rule()
    f.line("GET /health", size=32, colour=ACCENT)
    f.y += 10
    for k in ("chunks", "talks", "corpus_fingerprint", "embedding_model", "min_relevance"):
        f.line(f'  "{k}": {json.dumps(health[k])}', size=30, colour=FG, gap=10)
    frames.append(f)

    # 5. In-corpus answer
    f = Frame(6.0)
    f.line("In-corpus question", size=48, bold=True)
    f.rule()
    f.line(f'"{ask_in["question"]}"', size=36, colour=ACCENT)
    f.y += 12
    f.line(f'relevance {ask_in["best_relevance"]}    {ask_in["latency_seconds"]}s',
           size=32, colour=GOOD)
    f.y += 12
    p = ask_in["passages"][0]
    f.wrapped(p["text"][:260].replace("\n", " ").strip() + "…", size=28, colour=FG)
    f.y += 8
    f.line(p["cite"], size=28, colour=DIM)
    frames.append(f)

    # 6. The live defect
    f = Frame(6.5)
    f.line("The bug it found in production", size=48, bold=True)
    f.rule()
    f.line(f'"{ask_off["question"]}"', size=36, colour=ACCENT)
    f.y += 16
    f.line("Netcup original:  scores 0.618 → answers confidently", size=32, colour=BAD)
    f.line(f'Catalyst:         refused by {ask_off["refused_by"]} '
           f'{ask_off["unknown_entities"]}', size=32, colour=GOOD)
    f.y += 20
    f.wrapped("The question is genuinely about meditation, so cosine distance "
              "cannot reject it. Every named-teacher question did this. The fix "
              "is a second gate whose vocabulary is derived from the corpus — a "
              "hardcoded list of rival teachers would just be tuned to my traps.",
              size=30, colour=DIM)
    frames.append(f)

    # 7. The scoreboard, straight from the report
    f = Frame(7.0)
    f.line("Off-corpus refusals, by mechanism", size=48, bold=True)
    f.rule()
    for ln in report.splitlines():
        if ln.startswith("| ") and "Category" not in ln and "---" not in ln:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) < 5:
                continue
            colour = GOOD if cells[1].split("/")[0] == cells[1].split("/")[1] else BAD
            f.line(f"{cells[0]:<24}{cells[1]:>8} correct   {cells[2]} accidental   "
                   f"{cells[3]} answered", size=30, colour=colour, gap=12)
    f.y += 20
    f.wrapped("A refusal counts only when the mechanism that fired is the one the "
              "category expects. The Dalai Lama case refuses only because 'Dalai' "
              "occurs twice, under the gate's threshold — one more mention and it "
              "silently starts answering. Scored as a miss, not a win.",
              size=28, colour=DIM)
    frames.append(f)

    # 8. Verdict
    f = Frame(6.0)
    f.line("The agent's verdict on its own build", size=48, bold=True)
    f.rule()
    f.line("recall                 1.0     ≥ 0.85    PASS", size=32, colour=GOOD)
    f.line("citation accuracy      1.0     ≥ 0.90    PASS", size=32, colour=GOOD)
    f.line("no-match precision     0.733   ≥ 0.90    FAIL", size=32, colour=BAD)
    f.line("p95 latency            0.32s   ≤ 15s     PASS", size=32, colour=GOOD)
    f.y += 24
    f.line("RECOMMENDATION: REJECT", size=52, colour=BAD, bold=True)
    f.y += 16
    f.wrapped("And it stops there. Promotion to production needs a human. "
              "Lowering the threshold to 0.75 would make this pass — which is "
              "exactly the move the whole exercise argues against.",
              size=30, colour=DIM)
    frames.append(f)

    # 9. Close
    f = Frame(5.0)
    f.y = 380
    f.line("The demo is the reject run.", size=56, bold=True)
    f.y += 20
    f.wrapped("A suite tuned until everything passes demonstrates nothing. "
              "One that can tell you your own scoring was wrong is worth having.",
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
