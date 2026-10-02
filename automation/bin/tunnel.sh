#!/usr/bin/env bash
# Runs the Cloudflare Tunnel for sepahanfelezseo.lenzit.ir with the token from .env.
# The token goes through the TUNNEL_TOKEN environment variable, never the command line.
set -euo pipefail
ENV_FILE="$(dirname "$0")/../../.env"
TUNNEL_TOKEN="$(grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
if [ -z "$TUNNEL_TOKEN" ]; then
  echo "CLOUDFLARE_TUNNEL_TOKEN is empty in .env — tunnel not started"; exit 0
fi
export TUNNEL_TOKEN
exec "$HOME/.local/bin/cloudflared" tunnel --no-autoupdate run
