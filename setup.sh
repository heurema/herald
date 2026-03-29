#!/usr/bin/env bash
# setup.sh — herald plugin setup
# Usage: bash setup.sh [--preset NAME] [--time HH:MM] [--no-schedule] [--blank]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Defaults
PRESET="ai-engineering"
SCHEDULE_TIME="06:00"
NO_SCHEDULE=false

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --preset) PRESET="$2"; shift 2 ;;
        --time) SCHEDULE_TIME="$2"; shift 2 ;;
        --no-schedule) NO_SCHEDULE=true; shift ;;
        --blank) PRESET="blank"; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== herald setup ==="
echo ""

# --- Preflight checks ---

echo "[1/6] Preflight checks..."

# Python >= 3.10
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ required, found $PY_VERSION"
    exit 1
fi
echo "  Python $PY_VERSION OK"

# Package installer: prefer uv, fall back to pip
USE_UV=false
if command -v uv &>/dev/null; then
    USE_UV=true
    echo "  uv $(uv --version 2>/dev/null | head -1) OK"
elif python3 -m pip --version &>/dev/null; then
    echo "  pip OK"
else
    echo "ERROR: Neither uv nor pip found. Install uv (recommended) or pip."
    exit 1
fi

# Internet connectivity
if ! python3 -c "import urllib.request; urllib.request.urlopen('https://pypi.org', timeout=5)" 2>/dev/null; then
    echo "  WARNING: Cannot reach pypi.org. Offline install may fail."
else
    echo "  Internet OK"
fi

echo ""

# --- Resolve XDG paths ---

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/herald"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/herald"
VENV_DIR="$DATA_DIR/.venv"

# --- Create venv ---

echo "[2/6] Creating virtual environment at $VENV_DIR..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    if [ "$USE_UV" = true ]; then
        uv venv "$VENV_DIR"
    else
        python3 -m venv "$VENV_DIR"
    fi
    echo "  Created"
else
    echo "  Already exists"
fi

# --- Install dependencies ---

echo "[3/6] Installing dependencies..."
if [ "$USE_UV" = true ]; then
    uv pip install -q -r "$SCRIPT_DIR/src/pipeline/requirements.txt" --python "$VENV_DIR/bin/python"
else
    "$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/src/pipeline/requirements.txt"
fi
echo "  Installed"

# --- Copy config ---

echo "[4/6] Setting up config at $CONFIG_DIR..."
mkdir -p "$CONFIG_DIR"

# Validate schedule time: HH:MM format (hour 0-23, minute 0-59)
if ! [[ "$SCHEDULE_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    echo "ERROR: Invalid time '$SCHEDULE_TIME'. Use HH:MM format (e.g., 06:00)."
    exit 1
fi

if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    if [ "$PRESET" = "blank" ]; then
        cat > "$CONFIG_DIR/config.yaml" <<'EOF'
# herald config — blank preset
# Add your own feeds and keywords below.
version: 1
preset: "blank"
schedule_time: "06:00"
timezone: "local"
max_items: 10

# add_feeds:
#   - name: "My Blog"
#     url: "https://myblog.com/feed"
#     tier: 1
#     weight: 0.20

# add_keywords:
#   my_topic:
#     - "keyword1"
#     - "keyword2"
EOF
    else
        # Validate preset name: alphanumeric, hyphens, underscores only
        if ! [[ "$PRESET" =~ ^[a-zA-Z0-9_-]+$ ]]; then
            echo "ERROR: Invalid preset name '$PRESET'. Use only letters, numbers, hyphens, underscores."
            exit 1
        fi
        cat > "$CONFIG_DIR/config.yaml" <<'ENDOFCONFIG'
# herald config — customize by adding/removing feeds and keywords below.
version: 1
ENDOFCONFIG
        # Append user-chosen values safely (no shell expansion)
        printf 'preset: "%s"\n' "$PRESET" >> "$CONFIG_DIR/config.yaml"
        printf 'schedule_time: "%s"\n' "$SCHEDULE_TIME" >> "$CONFIG_DIR/config.yaml"
        cat >> "$CONFIG_DIR/config.yaml" <<'ENDOFCONFIG'
timezone: "local"
max_items: 10

# User overrides (layered on top of preset)
# add_feeds:
#   - name: "My Custom Blog"
#     url: "https://myblog.com/feed"
#     tier: 1
#     weight: 0.25
#
# remove_feeds:
#   - "r/MachineLearning"
#
# add_keywords:
#   my_topic:
#     - "kubernetes"
#
# remove_keywords:
#   - ai_finance

# Optional: Tavily API key (free tier, not required)
# tavily_api_key: ""
ENDOFCONFIG
    fi
    echo "  Config created"
else
    echo "  Config already exists"
fi

# --- Create data dirs ---

echo "[5/6] Creating data directories..."
mkdir -p "$DATA_DIR/data/raw" "$DATA_DIR/data/digests" "$DATA_DIR/data/state"
echo "  Directories created"

# --- Install scheduler ---

if [ "$NO_SCHEDULE" = true ]; then
    echo "[6/6] Scheduler skipped (--no-schedule)"
else
    echo "[6/6] Installing scheduler ($SCHEDULE_TIME daily)..."
    RUN_SH="$SCRIPT_DIR/src/pipeline/run.sh"
    chmod +x "$RUN_SH"

    CN_SCHEDULE_TIME="$SCHEDULE_TIME" CN_RUN_SH="$RUN_SH" \
    PYTHONPATH="$SCRIPT_DIR/src" "$VENV_DIR/bin/python" -c "
import os
from pipeline.scheduler import install_scheduler
ok = install_scheduler(os.environ['CN_SCHEDULE_TIME'], os.environ['CN_RUN_SH'])
print('  Scheduler installed' if ok else '  WARNING: Scheduler installation failed')
"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Privacy notice: This plugin fetches RSS feeds and public APIs daily."
echo "All data stays local at $DATA_DIR"
echo "No paid API keys required."
echo ""
echo "Next steps:"
echo "  1. Run /news-run to test the pipeline"
echo "  2. Run /news-digest to read results"
echo "  3. Edit $CONFIG_DIR/config.yaml to customize"
