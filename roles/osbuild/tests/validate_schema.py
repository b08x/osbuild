#!/usr/bin/env python3
"""Validate every component file under files/<distro>/<major>/<arch>/components/.

Checks the schema documented in defaults/main.yml: label and a non-empty
packages list are required, the other list fields are optional, unknown keys
are errors, and a named fragment must exist next to the component.
Exit status is 1 when any file fails.
"""
import sys
from pathlib import Path

import yaml

FILES = Path(__file__).resolve().parent.parent / "files"
LIST_FIELDS = ["packages", "repo_urls", "services", "kernel_args", "flatpaks", "bootc_repos", "copr_repos",
               "user_groups", "openscap_unselected"]
KNOWN = {"label", "fragment", *LIST_FIELDS}


def check(path):
    errors = []
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return ["not a mapping"]
    if not isinstance(data.get("label"), str) or not data["label"]:
        errors.append("label must be a non-empty string")
    if not data.get("packages"):
        errors.append("packages must be a non-empty list")
    for key in LIST_FIELDS:
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            errors.append(f"{key} must be a list of strings")
    unknown = set(data) - KNOWN
    if unknown:
        errors.append(f"unknown keys: {', '.join(sorted(unknown))}")
    fragment = data.get("fragment")
    if fragment and not (path.parent / fragment).is_file():
        errors.append(f"fragment {fragment} not found")
    dupes = {p for p in data.get("packages") or [] if (data["packages"]).count(p) > 1}
    if dupes:
        errors.append(f"duplicate packages: {', '.join(sorted(dupes))}")
    return errors


def main():
    files = sorted(FILES.glob("*/*/*/components/*.yml"))
    failed = 0
    for path in files:
        errors = check(path)
        if errors:
            failed += 1
            print(f"FAIL {path.relative_to(FILES)}: {'; '.join(errors)}")
    print(f"{len(files)} component files, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
