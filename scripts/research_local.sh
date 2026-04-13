#!/usr/bin/env bash
# End-to-end local research: sync data from VPS + run pipeline offline.
#
# Usage:
#   ./scripts/research_local.sh                          # sync + research
#   ./scripts/research_local.sh --skip-sync              # use existing local data
#   ./scripts/research_local.sh --days 270 --families rsi_momentum
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SKIP_SYNC=false
SYNC_ARGS=""
RESEARCH_ARGS="--all --max-per-family 5 --days 180"

# Parse arguments — forward --days/--pairs/--quality-pairs to BOTH sync and research
PREV_ARG=""
for arg in "$@"; do
    case "$arg" in
        --skip-sync) SKIP_SYNC=true ;;
        --days|--pairs|--quality-pairs)
            SYNC_ARGS="$SYNC_ARGS $arg"
            RESEARCH_ARGS="$RESEARCH_ARGS $arg"
            PREV_ARG="shared" ;;
        --families|--max-per-family|--interval|--db-path)
            RESEARCH_ARGS="$RESEARCH_ARGS $arg"
            PREV_ARG="research" ;;
        *)
            # Route the value following a flag to the right target(s)
            case "$PREV_ARG" in
                shared) SYNC_ARGS="$SYNC_ARGS $arg"; RESEARCH_ARGS="$RESEARCH_ARGS $arg" ;;
                *) RESEARCH_ARGS="$RESEARCH_ARGS $arg" ;;
            esac
            PREV_ARG="" ;;
    esac
done

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/research_local_${TIMESTAMP}.log"
mkdir -p logs

echo "╔══════════════════════════════════════════════════╗"
echo "║     Cryptopass Local Research Pipeline           ║"
echo "╚══════════════════════════════════════════════════╝"

# Step 1: Sync data from VPS
if [ "$SKIP_SYNC" = false ]; then
    echo ""
    echo "Phase 1: Syncing data from VPS..."
    ./scripts/sync_research_data.sh $SYNC_ARGS
else
    echo ""
    echo "Phase 1: Skipped (--skip-sync)"
fi

# Step 2: Run research offline
echo ""
echo "Phase 2: Starting offline research pipeline..."
echo "  Log: ${LOG_FILE}"
echo "  Args: --offline ${RESEARCH_ARGS}"
echo ""

nohup uv run python run_research.py --offline ${RESEARCH_ARGS} \
    > "$LOG_FILE" 2>&1 &

PID=$!
echo "╔══════════════════════════════════════════════════╗"
echo "║  🚀 Research running! PID: ${PID}               "
echo "║                                                  ║"
echo "║  Monitor: tail -f ${LOG_FILE}                    "
echo "║  Check:   ps -p ${PID}                           "
echo "║  Stop:    kill ${PID}                            ║"
echo "╚══════════════════════════════════════════════════╝"
