#!/usr/bin/env python3
"""Validate component definitions schema.
Jinja2 template expressions (strings matching {{ ... }}) are accepted
for list fields since they resolve to lists at Ansible runtime."""
import re
import sys

import yaml

import os

JINJA2_RE = re.compile(r"\{\{.*\}\}")

defaults_path = os.path.join(os.path.dirname(__file__), "../defaults/main.yml")
with open(defaults_path) as f:
    data = yaml.safe_load(f)

defs = data["osbuild_component_defs"]
print(f"Total components: {len(defs)}")
print()

REQUIRED_FIELDS = [
    "label",
    "packages",
    "blueprint_groups",
    "services",
    "kernel_args",
    "sources",
    "files",
    "flatpaks",
    "copr_repos",
    "bootc_repos",
    "requires",
    "conflicts",
    "size_impact",
    "build_time_impact",
    "secure_boot_compatible",
    "bootc_only",
    "blueprint_only",
]

# These fields should be either a literal list OR a Jinja2 expression resolving to a list
LIST_FIELDS = [
    "blueprint_groups",
    "services",
    "kernel_args",
    "sources",
    "files",
    "flatpaks",
    "copr_repos",
    "bootc_repos",
    "requires",
    "conflicts",
]

VALID_SIZE = {"none", "small", "medium", "large"}
VALID_BUILD = {"none", "low", "medium", "high"}

all_ok = True
for name, comp in sorted(defs.items()):
    missing = [f for f in REQUIRED_FIELDS if f not in comp]
    if missing:
        print(f"  FAIL {name}: missing {missing}")
        all_ok = False
        continue

    for lf in LIST_FIELDS:
        val = comp[lf]
        is_list = isinstance(val, list)
        is_jinja2_list = isinstance(val, str) and JINJA2_RE.search(val)
        if not is_list and not is_jinja2_list:
            print(
                f"  FAIL {name}: {lf} is {type(val).__name__} ({val!r}), expected list or Jinja2 list expression"
            )
            all_ok = False

    if comp["size_impact"] not in VALID_SIZE:
        print(f'  FAIL {name}: size_impact={comp["size_impact"]!r} not in {VALID_SIZE}')
        all_ok = False

    if comp["build_time_impact"] not in VALID_BUILD:
        print(
            f'  FAIL {name}: build_time_impact={comp["build_time_impact"]!r} not in {VALID_BUILD}'
        )
        all_ok = False

    if not isinstance(comp["secure_boot_compatible"], bool):
        print(f"  FAIL {name}: secure_boot_compatible is not bool")
        all_ok = False

    if not isinstance(comp["bootc_only"], bool):
        print(f"  FAIL {name}: bootc_only is not bool")
        all_ok = False

    if not isinstance(comp["blueprint_only"], bool):
        print(f"  FAIL {name}: blueprint_only is not bool")
        all_ok = False

if all_ok:
    print("PASS: All 14 components validated successfully!")
    print()
    print(
        f'{"Component":20s} {"Requires":30s} {"Conflicts":25s} {"Size":8s} {"Build":8s} {"SB"} {"BO"} {"BPO"} {"Svc"} {"Src"}'
    )
    print("-" * 130)
    for name, comp in sorted(defs.items()):
        req = str(comp["requires"])
        conf = str(comp["conflicts"])
        si = comp["size_impact"]
        bti = comp["build_time_impact"]
        sb = "Y" if comp["secure_boot_compatible"] else "N"
        bo = "Y" if comp["bootc_only"] else "N"
        bpo = "Y" if comp["blueprint_only"] else "N"
        svc = len(comp["services"]) if isinstance(comp["services"], list) else "J2"
        src = len(comp["sources"]) if isinstance(comp["sources"], list) else "J2"
        print(
            f"{name:20s} {req:30s} {conf:25s} {si:8s} {bti:8s} {sb:3s} {bo:3s} {bpo:3s} {str(svc):>3s} {str(src):>3s}"
        )
    sys.exit(0)
else:
    print()
    print("FAIL: Validation errors found.")
    sys.exit(1)
