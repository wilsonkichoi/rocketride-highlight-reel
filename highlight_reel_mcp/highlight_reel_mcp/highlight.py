import os
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel
from google import genai


class CutSegment(BaseModel):
    file: str
    timestamp: str
    summary: str


class VideoAnalysis(BaseModel):
    overall_summary: str
    total_estimate_duration: int
    cut_segments: list[CutSegment]


def get_video_files(video_dir: str) -> list[Path]:
    dir_path = Path(video_dir).expanduser().resolve()
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {video_dir}")
    files = sorted(
        f
        for f in dir_path.iterdir()
        if f.is_file() and f.suffix.lower() in [".mov", ".mp4", ".avi", ".mkv"]
    )
    if not files:
        raise ValueError(f"No video files found in {video_dir}")
    return files


def upload_videos(files: list[Path], client: genai.Client) -> list:
    uploaded = []
    for f in files:
        uploaded.append(
            client.files.upload(
                file=f, config=genai.types.UploadFileConfig(display_name=f.name)
            )
        )
    return uploaded


def wait_for_processing(uploaded_files: list, client: genai.Client):
    while True:
        if all(
            client.files.get(name=f.name).state.name != "PROCESSING"
            for f in uploaded_files
        ):
            break
        time.sleep(2)


def analyze_with_ai(
    uploaded_files: list, filenames: list[str], client: genai.Client, model: str
) -> VideoAnalysis:
    file_list = "\n".join(f"- {name}" for name in filenames)
    prompt = f"""
**Act As:** Expert Video Content Analyst & Editor Assistant

**Goal:** Analyze the uploaded videos and select the best segments for a highlight reel that is approximately 30 seconds long.

**Available video files:**
{file_list}

**Instructions:**
- Watch all the videos to understand their flow and key points.
- Select multiple segments from across the videos. You MUST include enough segments so that their durations sum to approximately 30 seconds total.
- Each segment should be between 3 and 10 seconds long.
- Pick segments based on visual quality, action, and relevance.
- The "file" field MUST be one of the exact filenames listed above. Do NOT put timestamps or anything else in the "file" field.
- The "timestamp" field must be in "MM:SS - MM:SS" format representing start and end times within that file.
- The "total_estimate_duration" MUST be close to 30 (between 25 and 35).
- You MUST return multiple cut_segments so their durations sum to ~30 seconds.

**Output Format (JSON):**
```json
{{
    "overall_summary": "Brief overview of the video content and flow.",
    "total_estimate_duration": 30,
    "cut_segments": [
        {{
            "file": "<one of the filenames listed above>",
            "timestamp": "MM:SS - MM:SS",
            "summary": "Why this segment was chosen"
        }}
    ]
}}
```
"""
    response = client.models.generate_content(
        model=model,
        contents=[*uploaded_files, prompt],
        config={
            "response_mime_type": "application/json",
            "response_schema": VideoAnalysis,
        },
    )
    return VideoAnalysis.model_validate_json(response.text)


def analyze_videos(video_dir: str, api_key: str, model: str) -> VideoAnalysis:
    client = genai.Client(api_key=api_key)
    files = get_video_files(video_dir)
    filenames = [f.name for f in files]
    uploaded = upload_videos(files, client)
    wait_for_processing(uploaded, client)
    analysis = analyze_with_ai(uploaded, filenames, client, model)
    for f in client.files.list():
        client.files.delete(name=f.name)
    return analysis


def parse_timestamp(timestamp_str: str) -> tuple[float, float]:
    start_str, end_str = timestamp_str.split(" - ")

    def time_to_seconds(time_str: str) -> float:
        parts = time_str.strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        raise ValueError(f"Invalid timestamp format: {time_str}")

    return time_to_seconds(start_str), time_to_seconds(end_str)


def create_highlight_clip(
    video_dir: str, cut_segments: list[dict], output_path: str
) -> str:
    files = get_video_files(video_dir)
    file_map = {f.name: f for f in files}

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = ["ffmpeg"]
    filter_parts = []
    valid_segments = []

    for segment in cut_segments:
        filename = segment["file"]
        if filename not in file_map:
            continue

        input_file = file_map[filename]
        start_time, end_time = parse_timestamp(segment["timestamp"])
        duration = end_time - start_time

        idx = len(valid_segments)
        valid_segments.append(segment)

        cmd.extend(["-ss", str(start_time), "-t", str(duration), "-i", str(input_file)])

        filter_parts.append(
            f"[{idx}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS-STARTPTS[v{idx}]"
        )
        filter_parts.append(
            f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{idx}]"
        )

    if not valid_segments:
        raise ValueError("No valid segments to process")

    n = len(valid_segments)
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]")

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-crf",
            "23",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-y",
            output_path,
        ]
    )

    subprocess.run(cmd, check=True, capture_output=True)
    return output_path
