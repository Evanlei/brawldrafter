#!/usr/bin/env bash
# Copy local brawldrafter.db into a Railway volume at /data/brawldrafter.db
# Requires: railway CLI linked to your project, service running with volume mounted at /data
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="${1:-$ROOT/brawldrafter.db}"

if [ ! -f "$DB" ]; then
  echo "Database not found: $DB" >&2
  exit 1
fi

if ! command -v railway >/dev/null 2>&1; then
  echo "Install Railway CLI: https://docs.railway.com/develop/cli" >&2
  exit 1
fi

SERVICE="${RAILWAY_SERVICE:-brawldrafter}"

echo "Uploading $DB ($(wc -c < "$DB" | tr -d ' ') bytes) to /data/brawldrafter.db ..."
echo "Service: $SERVICE (override with RAILWAY_SERVICE=...)"
echo ""
echo "In Railway dashboard first: Service → Volumes → Add volume → Mount path /data"
echo ""

# Parent dir must exist; volume mount creates /data once attached.
railway ssh -s "$SERVICE" -- "mkdir -p /data && ls -la /data"
cat "$DB" | railway ssh -s "$SERVICE" -- "tee /data/brawldrafter.db > /dev/null"
railway ssh -s "$SERVICE" -- "ls -la /data/brawldrafter.db"
echo "Done. Redeploy or restart the service, then: curl https://YOUR-DOMAIN/api/v1/modes"
