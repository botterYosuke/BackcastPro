#!/bin/sh
# update が部分失敗 (exit 1) でも split を必ず実行し、
# どちらかが失敗した場合は全体を exit 1 で終了する
set -u

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

FAILED=0

log "=== update_stocks_price.py 開始 ==="
python /app/update_stocks_price.py "$@" || FAILED=1
log "=== update_stocks_price.py 終了 (exit=$FAILED) ==="

log "=== split_only.py 開始 ==="
python /app/split_only.py || FAILED=1
log "=== split_only.py 終了 (exit=$FAILED) ==="

exit $FAILED