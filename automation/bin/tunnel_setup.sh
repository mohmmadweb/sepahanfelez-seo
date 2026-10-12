#!/usr/bin/env bash
# One-time Cloudflare Tunnel setup for sepahanfelezseo.lenzit.ir.
#  1) `cloudflared tunnel login` prints a link — the owner opens it and authorises the lenzit.ir zone
#  2) then, automatically: create tunnel, write ingress config, point the DNS name at the tunnel
#     (replacing the old GitHub Pages CNAME), save the tunnel token in .env (backup), restart the service.
set -uo pipefail
CF="$HOME/.local/bin/cloudflared"; NAME="sepahanfelez-seo"; HOST="sepahanfelezseo.lenzit.ir"
DIR="$HOME/.cloudflared"; ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; LOG="$ROOT/dashboard/data/tunnel_setup.log"
mkdir -p "$DIR" "$(dirname "$LOG")"; chmod 700 "$DIR"
echo "[$(date -Is)] start" >> "$LOG"
if [ ! -f "$DIR/cert.pem" ]; then
  "$CF" tunnel login >> "$LOG" 2>&1 || { echo "[$(date -Is)] login failed" >> "$LOG"; exit 1; }
fi
chmod 600 "$DIR/cert.pem"
if ! "$CF" tunnel info "$NAME" >/dev/null 2>&1; then
  "$CF" tunnel create "$NAME" >> "$LOG" 2>&1 || { echo "[$(date -Is)] create failed" >> "$LOG"; exit 1; }
fi
ID="$("$CF" tunnel list -o json 2>/dev/null | python3 -c "import json,sys;print(next(t['id'] for t in json.load(sys.stdin) if t['name']=='$NAME'))")"
cat > "$DIR/$NAME.yml" <<YML
protocol: http2
tunnel: $ID
credentials-file: $DIR/$ID.json
ingress:
  - hostname: $HOST
    service: http://localhost:8813
  - service: http_status:404
YML
chmod 600 "$DIR/$ID.json" "$DIR/$NAME.yml" 2>/dev/null
"$CF" tunnel route dns --overwrite-dns "$NAME" "$HOST" >> "$LOG" 2>&1 || { echo "[$(date -Is)] dns failed" >> "$LOG"; exit 1; }
TOKEN="$("$CF" tunnel token "$NAME" 2>/dev/null)"
if [ -n "$TOKEN" ]; then
  "$ROOT/.venv/bin/python" - "$TOKEN" <<'PY'
import sys; sys.path.insert(0, "dashboard/server")
import os; os.chdir(os.path.dirname(os.path.abspath("dashboard")))
import envfile; envfile.update({"CLOUDFLARE_TUNNEL_TOKEN": sys.argv[1]})
PY
fi
systemctl --user restart sepahanfelez-tunnel.service
echo "[$(date -Is)] done tunnel=$ID" >> "$LOG"
