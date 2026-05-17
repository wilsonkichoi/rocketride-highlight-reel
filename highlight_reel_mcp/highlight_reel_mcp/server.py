import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from mcp.server import Server
from mcp.types import TextContent, Tool

from .highlight import analyze_videos, create_highlight_clip

load_dotenv(find_dotenv(usecwd=True))

server = Server("highlight-reel")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="analyze_videos",
            description="Upload videos to Gemini AI and get highlight cut recommendations. Returns JSON with overall_summary, total_estimate_duration, and cut_segments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_dir": {
                        "type": "string",
                        "description": "Directory containing video files (.mov, .mp4, etc.)",
                    },
                    "model": {
                        "type": "string",
                        "description": "Gemini model to use",
                        "default": "gemini-2.5-flash-lite",
                    },
                },
                "required": ["video_dir"],
            },
        ),
        Tool(
            name="create_highlight",
            description="Run ffmpeg to extract and concatenate video segments into a highlight reel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_dir": {
                        "type": "string",
                        "description": "Directory containing the source video files",
                    },
                    "cut_segments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "timestamp": {"type": "string"},
                                "summary": {"type": "string"},
                            },
                            "required": ["file", "timestamp"],
                        },
                        "description": "Segments from analyze_videos result",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Output file path for the highlight video",
                    },
                },
                "required": ["video_dir", "cut_segments", "output_path"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "analyze_videos":
        video_dir = arguments["video_dir"]
        model = arguments.get("model", "gemini-2.5-flash-lite")
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return [TextContent(type="text", text="Error: GEMINI_API_KEY environment variable not set")]

        analysis = analyze_videos(video_dir, api_key, model)
        return [TextContent(type="text", text=analysis.model_dump_json(indent=2))]

    elif name == "create_highlight":
        video_dir = arguments["video_dir"]
        cut_segments = arguments["cut_segments"]
        output_path = arguments["output_path"]

        result_path = create_highlight_clip(video_dir, cut_segments, output_path)
        return [TextContent(type="text", text=f"Highlight reel created: {result_path}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]
