"""Video frame extraction and classification using ffmpeg + Claude API."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

FRAME_MODEL = "claude-haiku-4-5-20251001"
FRAME_INTERVAL_SECONDS = 15


@dataclass
class Frame:
    """A single extracted video frame with classification."""

    path: Path
    timestamp_seconds: float
    classification: str = "unclassified"
    details: dict = field(default_factory=dict)


@dataclass
class VideoAnalysis:
    """Complete video analysis result."""

    frames: list[Frame] = field(default_factory=list)
    duration_seconds: float = 0.0
    screen_share_detected: bool = False
    tools_observed: list[str] = field(default_factory=list)
    mcp_tools_used: bool = False
    grep_cat_observed: bool = False


def get_video_duration(video_path: str | Path) -> float:
    """Get video duration in seconds using ffprobe."""
    video_path = Path(video_path).resolve()
    if not video_path.is_file():
        return 0.0
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", "--", str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    interval: int = FRAME_INTERVAL_SECONDS,
) -> list[Frame]:
    """Extract frames from a video at regular intervals using ffmpeg."""
    video_path = Path(video_path).resolve()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = get_video_duration(video_path)

    subprocess.run(
        [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",
            str(output_dir / "frame_%04d.jpg"),
        ],
        capture_output=True,
    )

    frames: list[Frame] = []
    for frame_file in sorted(output_dir.glob("frame_*.jpg")):
        idx = int(frame_file.stem.split("_")[1]) - 1
        ts = idx * interval
        frames.append(Frame(path=frame_file, timestamp_seconds=ts))

    return frames


def classify_frame(client: anthropic.Anthropic, frame: Frame) -> Frame:
    """Classify a single frame using Claude vision API."""
    image_data = base64.b64encode(frame.path.read_bytes()).decode("utf-8")

    response = client.messages.create(
        model=FRAME_MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                },
                {
                    "type": "text",
                    "text": (
                        "Classify this video frame from a user testing session. "
                        "Return JSON with:\n"
                        '{"classification": "<one of: screen_share_ide, screen_share_website, '
                        "screen_share_github, screen_share_output, webcam_tester, webcam_facilitator, "
                        'webcam_both, no_screen_share>",\n'
                        '"details": {\n'
                        '  "ide_visible": "<Cursor|Codex|VS Code|Claude Code|none>",\n'
                        '  "rubberduck_tools_visible": ["<tool names if visible>"],\n'
                        '  "grep_cat_commands_visible": <boolean>,\n'
                        '  "use_case_exercised": "<UC-XX or null>",\n'
                        '  "expression": "<engaged|confused|surprised|neutral|frustrated|not_visible>"\n'
                        "}}\n"
                        "Return ONLY valid JSON."
                    ),
                },
            ],
        }],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]

    try:
        data = json.loads(text.strip())
        frame.classification = data.get("classification", "unclassified")
        frame.details = data.get("details", {})
    except json.JSONDecodeError:
        frame.classification = "unclassified"
        frame.details = {"error": "Failed to parse frame classification"}

    return frame


def analyze_video(
    video_path: str | Path,
    output_dir: str | Path | None = None,
) -> VideoAnalysis:
    """Full video analysis pipeline: extract frames, classify, summarize."""
    video_path = Path(video_path)
    client = anthropic.Anthropic()

    if output_dir is None:
        tmp = tempfile.mkdtemp(prefix="rd_frames_")
        output_dir = Path(tmp)

    print("Extracting video frames...", file=sys.stderr)
    frames = extract_frames(video_path, output_dir)
    duration = get_video_duration(video_path)

    print(f"Classifying {len(frames)} frames...", file=sys.stderr)
    classified: list[Frame] = []
    for i, frame in enumerate(frames):
        if i % 10 == 0:
            print(f"  Frame {i+1}/{len(frames)}...", file=sys.stderr)
        classify_frame(client, frame)
        classified.append(frame)

    # Aggregate results
    tools_observed: set[str] = set()
    grep_cat_seen = False
    screen_share = False

    for frame in classified:
        if frame.classification.startswith("screen_share"):
            screen_share = True
        rd_tools = frame.details.get("rubberduck_tools_visible", [])
        if rd_tools:
            tools_observed.update(rd_tools)
        if frame.details.get("grep_cat_commands_visible"):
            grep_cat_seen = True

    return VideoAnalysis(
        frames=classified,
        duration_seconds=duration,
        screen_share_detected=screen_share,
        tools_observed=sorted(tools_observed),
        mcp_tools_used=bool(tools_observed),
        grep_cat_observed=grep_cat_seen,
    )


def video_analysis_to_dict(analysis: VideoAnalysis) -> dict:
    """Convert VideoAnalysis to a JSON-serializable dict."""
    return {
        "duration_seconds": analysis.duration_seconds,
        "duration_minutes": round(analysis.duration_seconds / 60, 1),
        "frame_count": len(analysis.frames),
        "screen_share_detected": analysis.screen_share_detected,
        "tools_observed": analysis.tools_observed,
        "mcp_tools_used": analysis.mcp_tools_used,
        "grep_cat_observed": analysis.grep_cat_observed,
        "frame_classifications": [
            {
                "timestamp_seconds": f.timestamp_seconds,
                "classification": f.classification,
                "details": f.details,
            }
            for f in analysis.frames
        ],
    }
