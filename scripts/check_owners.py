#!/usr/bin/env python3
"""Block commits that touch files owned by someone else (rules in the OWNERS file).

Run automatically by .githooks/pre-commit. One-time setup on each PC:

    git config core.hooksPath .githooks
    git config cityecho.role A          # or B or C

Shared (frozen) files may only change in a commit of their own, with:

    CITYECHO_SHARED=1 git commit -m "..."

Manual checks:
    python3 scripts/check_owners.py          # check the staged files (what the hook does)
    python3 scripts/check_owners.py --all    # list tracked files that no OWNERS rule covers

Standard library only, so it runs with any python3.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES = {"A": "📱 Mobile", "B": "🖥️ Web admin", "C": "📡 Sensors and data"}


def glob_to_regex(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def load_rules() -> list[tuple[str, re.Pattern, str]]:
    rules = []
    for line in (ROOT / "OWNERS").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, owner = line.split()
        rules.append((pattern, glob_to_regex(pattern), owner))
    return rules


def owner_of(path: str, rules) -> str | None:
    for _, rx, owner in rules:
        if rx.match(path):
            return owner
    return None


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def staged_paths() -> list[str]:
    paths: list[str] = []
    for line in git("diff", "--cached", "--name-status", "-M"):
        parts = line.split("\t")
        paths.extend(parts[1:])  # renames list both the old and the new path
    return sorted(set(paths))


def main() -> int:
    rules = load_rules()

    if "--all" in sys.argv:
        files = sorted(set(git("ls-files")) | set(git("ls-files", "--others", "--exclude-standard")))
        missing = [f for f in files if owner_of(f, rules) is None]
        for f in missing:
            print(f"  no owner: {f}")
        print(f"{len(files)} files, {len(missing)} without an owner")
        return 1 if missing else 0

    configured = subprocess.run(["git", "config", "--get", "cityecho.role"], cwd=ROOT,
                                capture_output=True, text=True).stdout  # exits 1 when unset
    role = (os.environ.get("CITYECHO_ROLE") or configured).strip().upper()
    if role not in ROLES:
        print("✋ Your role is not set. Run once:  git config cityecho.role A   (A, B or C)")
        return 1

    paths = staged_paths()
    if not paths:
        return 0
    shared_ok = os.environ.get("CITYECHO_SHARED") == "1"
    owners = {p: owner_of(p, rules) for p in paths}

    unknown = [p for p, o in owners.items() if o is None]
    shared = [p for p, o in owners.items() if o == "SHARED"]
    foreign = [(p, o) for p, o in owners.items() if o not in (None, "SHARED", role)]
    own = [p for p, o in owners.items() if o == role]
    problems: list[str] = []

    if unknown:
        problems.append("Files with no owner in OWNERS (add them to OWNERS first, in a SHARED commit):")
        problems += [f"    {p}" for p in unknown]
    if foreign:
        problems.append(f"These files belong to someone else (you are {role} = {ROLES[role]}):")
        problems += [f"    {p}  →  {o} ({ROLES[o]})" for p, o in foreign]
    if shared and not shared_ok:
        problems.append("Shared (frozen) files. Announce it in the group, then commit them on their own:  CITYECHO_SHARED=1 git commit ...")
        problems += [f"    {p}" for p in shared]
    if shared and shared_ok and own:
        problems.append("Shared files can't be in the same commit as your own files. Make two separate commits:")
        problems += [f"    shared: {p}" for p in shared] + [f"    yours: {p}" for p in own]

    if problems:
        print("✋ Commit blocked (CityEcho file ownership, OWNERS):")
        print("\n".join(problems))
        print("If someone else's file needs a change, tell its owner; don't change it yourself.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
