#!/usr/bin/env bash
# setup.sh — claude-news plugin setup
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

echo "=== claude-news setup ==="
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

# pip
if ! python3 -m pip --version &>/dev/null; then
    echo "ERROR: pip not found. Install pip."
    exit 1
fi
echo "  pip OK"

# Internet connectivity
if ! python3 -c "import urllib.request; urllib.request.urlopen('https://pypi.org', timeout=5)" 2>/dev/null; then
    echo "  WARNING: Cannot reach pypi.org. Offline install may fail."
else
    echo "  Internet OK"
fi

echo ""

# --- Resolve XDG paths ---

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/claude-news"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/claude-news"
VENV_DIR="$DATA_DIR/.venv"

# --- Create venv ---

echo "[2/6] Creating virtual environment at $VENV_DIR..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  Created"
else
    echo "  Already exists"
fi

# --- Install dependencies ---

echo "[3/6] Installing dependencies..."
"$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/pipeline/requirements.txt"
echo "  Installed"

# --- Copy config ---

echo "[4/6] Setting up config at $CONFIG_DIR..."
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    if [ "$PRESET" = "blank" ]; then
        cat > "$CONFIG_DIR/config.yaml" <<'EOF'
# claude-news config — blank preset
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
        cat > "$CONFIG_DIR/config.yaml" <<EOF
# claude-news config — based on "$PRESET" preset
# Customize by adding/removing feeds and keywords below.
version: 1
preset: "$PRESET"
schedule_time: "$SCHEDULE_TIME"
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
EOF
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
    RUN_SH="$SCRIPT_DIR/pipeline/run.sh"
    chmod +x "$RUN_SH"

    CN_SCHEDULE_TIME="$SCHEDULE_TIME" CN_RUN_SH="$RUN_SH" \
    PYTHONPATH="$SCRIPT_DIR" "$VENV_DIR/bin/python" -c "
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
echo "  1. Run /news run to test the pipeline"
echo "  2. Run /news digest to read results"
echo "  3. Edit $CONFIG_DIR/config.yaml to customize"
