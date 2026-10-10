#!/usr/bin/env bash
# Runs the Cloudflare Tunnel for sepahanfelezseo.lenzit.ir.
# Prefers the local config written by tunnel_setup.sh; falls back to CLOUDFLARE_TUNNEL_TOKEN from .env
# (passed through the TUNNEL_TOKEN environment variable, never the command line).
set -euo pipefail
CONF="$HOME/.cloudflared/sepahanfelez-seo.yml"
if [ -f "$CONF" ]; then
  exec "$HOME/.local/bin/cloudflared" tunnel --no-autoupdate --config "$CONF" run
fi
ENV_FILE="$(dirname "$0")/../../.env"
TUNNEL_TOKEN="$(grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
if [ -z "$TUNNEL_TOKEN" ]; then
  echo "no tunnel config and CLOUDFLARE_TUNNEL_TOKEN is empty — tunnel not started"; exit 0
fi
export TUNNEL_TOKEN
exec "$HOME/.local/bin/cloudflared" tunnel --no-autoupdate run
