#!/usr/bin/env bash
# Sync research kline data from VPS to local machine.
#
# Usage:
#   ./scripts/sync_research_data.sh                     # default: 180 days, 15 pairs
#   ./scripts/sync_research_data.sh --days 270 --pairs 20
#   ./scripts/sync_research_data.sh --quality-pairs
#   ./scripts/sync_research_data.sh --sync-only          # skip VPS prefetch, just SCP
set -euo pipefail

VPS_HOST="fight-tres"
VPS_REPO="/home/vforvaick/pumpradar-bot"
VPS_PYTHON="${VPS_REPO}/.venv/bin/python"
VPS_CACHE="${VPS_REPO}/data/research_cache/"
LOCAL_CACHE="data/research_cache/"
PREFETCH_ARGS=""
SYNC_ONLY=false

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --sync-only) SYNC_ONLY=true ;;
        *) PREFETCH_ARGS="$PREFETCH_ARGS $arg" ;;
    esac
done

# Default args if none provided
if [ -z "$PREFETCH_ARGS" ] && [ "$SYNC_ONLY" = false ]; then
    PREFETCH_ARGS="--days 180 --pairs 15"
fi

echo "╔══════════════════════════════════════════════════╗"
echo "║       Cryptopass Research Data Sync              ║"
echo "╚══════════════════════════════════════════════════╝"

# Step 1: Clean local stale parquets
echo ""
echo "→ Step 1: Cleaning local stale parquets (>7 days)..."
find "$LOCAL_CACHE" -name "*.parquet" -mtime +7 -delete 2>/dev/null && \
    echo "  Cleaned stale parquets" || echo "  No stale parquets found"

# Step 2: Prefetch on VPS (unless --sync-only)
if [ "$SYNC_ONLY" = false ]; then
    echo ""
    echo "→ Step 2: Prefetching kline data on VPS..."
    echo "  Command: ${VPS_PYTHON} scripts/prefetch_klines_vps.py ${PREFETCH_ARGS}"

    if ! ssh "$VPS_HOST" "cd ${VPS_REPO} && ${VPS_PYTHON} scripts/prefetch_klines_vps.py ${PREFETCH_ARGS}"; then
        echo "  ⚠️  VPS prefetch failed! Will try to sync existing data..."
    fi
else
    echo ""
    echo "→ Step 2: Skipped (--sync-only)"
fi

# Step 3: SCP parquets to local
echo ""
echo "→ Step 3: Syncing parquets from VPS to local..."
mkdir -p "$LOCAL_CACHE"

if ! scp -r "${VPS_HOST}:${VPS_CACHE}"*.parquet "$LOCAL_CACHE" 2>/dev/null; then
    echo "  ❌ SCP failed! Check SSH connection to ${VPS_HOST}"
    echo "  Try: ssh ${VPS_HOST} ls ${VPS_CACHE}"
    exit 1
fi

# Step 4: Verify
echo ""
echo "→ Step 4: Verifying local cache..."
FILE_COUNT=$(find "$LOCAL_CACHE" -name "*.parquet" | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "$LOCAL_CACHE" 2>/dev/null | cut -f1)
HAS_BTC=$(find "$LOCAL_CACHE" -name "BTCUSDT_*.parquet" | wc -l | tr -d ' ')

echo "  Files: ${FILE_COUNT}"
echo "  Size: ${TOTAL_SIZE}"

if [ "$HAS_BTC" -eq 0 ]; then
    echo "  ⚠️  WARNING: BTCUSDT parquet missing! Research will fail."
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅ Sync complete! Ready for offline research.  ║"
echo "║                                                  ║"
echo "║  Run research:                                   ║"
echo "║  uv run python run_research.py --offline \\      ║"
echo "║    --all --max-per-family 5 --days 180           ║"
echo "╚══════════════════════════════════════════════════╝"
