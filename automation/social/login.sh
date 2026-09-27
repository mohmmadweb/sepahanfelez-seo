#!/usr/bin/env bash
# ورود تمیز به شبکه‌ها — مثال: automation/social/login.sh login eitaa  |  automation/social/login.sh status
cd "$(dirname "$0")/../.." && exec .venv/bin/python automation/social/login.py "$@"
