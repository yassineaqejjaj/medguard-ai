#!/usr/bin/env python3
"""Fails if a Python or production JavaScript dependency carries a licence outside the allowlist.

Policy (docs/licenses.md): permissive OSI licences only (Apache-2.0, MIT, BSD, ISC, PSF, PostgreSQL, 0BSD, MIT-0, Unlicense);
MPL-2.0 is tolerated as file-level weak copyleft when unmodified. GPL/AGPL/LGPL/SSPL/BUSL/proprietary are rejected.
Recorded exceptions are listed explicitly, with the reason, so they cannot slip in silently."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOW = re.compile(r"\b(MIT|BSD|Apache|ISC|PSF|Python Software Foundation|PostgreSQL|0BSD|Unlicense|Mozilla Public License 2\.0|MPL-2\.0)", re.I)
DENY = re.compile(r"\b(AGPL|GPL|LGPL|SSPL|BUSL|Commons Clause|Proprietary|UNKNOWN)\b", re.I)
EXCEPTIONS = {
    "caniuse-lite": "CC-BY-4.0 browser-support data, build-time only (not shipped in the runtime image); not OSI-approved",
    "certifi": "MPL-2.0 CA bundle, unmodified; file-level weak copyleft",
    "pyphen": "tri-licensed GPL-2.0+ / LGPL-2.1+ / MPL-1.1 (WeasyPrint dependency); used under MPL-1.1, unmodified",
}


def check(name: str, lic: str, problems: list[str]) -> None:
    if name in EXCEPTIONS:
        return
    parts = re.split(r";| AND | OR ", lic)
    if DENY.search(lic) and not all(ALLOW.search(p) for p in parts):  # "A OR B" is fine when one side is allowed
        problems.append(f"{name}: {lic}")
    elif not ALLOW.search(lic):
        problems.append(f"{name}: {lic} (not on the allowlist)")


def main() -> int:
    problems: list[str] = []
    py = json.loads(subprocess.check_output(["uv", "run", "pip-licenses", "--format=json"], cwd=ROOT / "apps/api", text=True))
    for p in py:
        if p["Name"] != "medguard-api":
            check(p["Name"], p["License"], problems)
    js = json.loads(subprocess.check_output(["pnpm", "licenses", "list", "--prod", "--json"], cwd=ROOT / "apps/web", text=True))
    n_js = 0
    for lic, pkgs in js.items():
        for p in pkgs:
            n_js += 1
            check(p["name"], lic, problems)
    print(f"checked {len(py) - 1} Python and {n_js} production JavaScript packages; exceptions: {sorted(EXCEPTIONS)}")
    for line in problems:
        print("  REJECTED", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
