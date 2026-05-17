#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export VIRTUAL_ENV=
exec uv run --directory "$SCRIPT_DIR" python -m highlight_reel_mcp
