"""Load the project's .env into os.environ (values already in the environment win).

Every credential lives in /home/ubuntu/projects/sepahanfelez-seo/.env (chmod 600, gitignored);
code only ever reads variable names. .env.example lists them without values.
"""

import os

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")


def load_env(path=ENV_PATH):
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if key.strip() and value:
                os.environ.setdefault(key.strip(), value)
    return True


def get(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default
