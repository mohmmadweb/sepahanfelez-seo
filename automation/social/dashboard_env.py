"""Bridge so automation/social can write per-account secrets through the dashboard's .env writer."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dashboard", "server"))
import envfile  # noqa: E402


def set_secrets(changes, drop=False):
    return envfile.set_account_secrets(changes, drop=drop)
