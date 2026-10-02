"""
.env editor for the dashboard.

The list of settings, their groups and descriptions come from .env.example (the template
in git). Values live only in .env (chmod 600). Secret values are write-only: the UI learns
whether one is set, never what it is.
"""

import os
import re
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV = os.path.join(ROOT, ".env")
EXAMPLE = os.path.join(ROOT, ".env.example")
SECRET_RE = re.compile(r"TOKEN|SECRET|PASSWORD|HASH|_KEY$|KEY_|CREDENTIALS|PROXY|STATE_KEY", re.I)
READ_ONLY = {"SF_STATE_KEY"}          # changing it orphans every encrypted backup; edit by hand if ever needed
LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def _read(path):
    vals = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = LINE.match(line.strip())
                if m:
                    vals[m.group(1)] = m.group(2).strip()
    return vals


def schema():
    """[{group, vars:[{name, help, secret, read_only}]}] in template order."""
    groups, cur, help_lines = [], None, []
    with open(EXAMPLE, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            g = re.match(r"^#\s*──\s*([^─\s].*?)\s*─", line)
            if g:
                cur = {"group": g.group(1).strip(), "vars": []}
                groups.append(cur)
                help_lines = []
                continue
            if line.startswith("#"):
                txt = line.lstrip("#").strip()
                if txt and not set(txt) <= set("─ "):
                    help_lines.append(txt)
                continue
            m = LINE.match(line.strip())
            if m and cur is not None:
                n = m.group(1)
                cur["vars"].append({"name": n, "help": " ".join(help_lines), "default": m.group(2).strip(),
                                    "secret": bool(SECRET_RE.search(n)), "read_only": n in READ_ONLY})
                help_lines = []
            elif not line.strip():
                help_lines = []
    return [g for g in groups if g["vars"]]


def view():
    vals = _read(ENV)
    out = []
    for g in schema():
        rows = []
        for v in g["vars"]:
            val = vals.get(v["name"], "")
            rows.append({**v, "set": bool(val), "value": None if v["secret"] else val})
        out.append({"group": g["group"], "vars": rows})
    return out


def update(changes):
    """changes: {NAME: value}. Empty string clears. Only names from the template are accepted."""
    allowed = {v["name"]: v for g in schema() for v in g["vars"]}
    bad = [k for k in changes if k not in allowed or allowed[k]["read_only"]]
    if bad:
        raise ValueError("این تنظیم قابل تغییر نیست: " + "، ".join(bad))
    for k, v in changes.items():
        if "\n" in str(v) or "\r" in str(v):
            raise ValueError(f"{k}: مقدار نباید چندخطی باشد")
    vals = _read(ENV)
    vals.update({k: str(v).strip() for k, v in changes.items()})

    # rewrite in template order, keeping the template's comments; unknown keys kept at the end
    lines, written = [], set()
    with open(EXAMPLE, encoding="utf-8") as fh:
        for raw in fh:
            m = LINE.match(raw.strip())
            if m:
                lines.append(f"{m.group(1)}={vals.get(m.group(1), '')}")
                written.add(m.group(1))
            else:
                lines.append(raw.rstrip("\n"))
    extra = [k for k in vals if k not in written]
    if extra:
        lines += ["", "# ── سایر ──"] + [f"{k}={vals[k]}" for k in extra]
    fd, tmp = tempfile.mkstemp(dir=ROOT, prefix=".env.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV)
    for k, v in changes.items():
        if str(v).strip():
            os.environ[k] = str(v).strip()
        else:
            os.environ.pop(k, None)
    return sorted(changes)
