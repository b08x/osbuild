#!/usr/bin/env python3
"""Check prepared blueprints for the injected first-login files.

Usage: check_injection.py OUTPUT_DIR FIRSTBOOT_SRC_DIR EXPECTED_COUNT

Every OUTPUT_DIR/*.toml must parse as TOML, contain each first-login path
exactly once, and carry `data` byte-identical to the source file.
"""
import pathlib
import sys
import tomllib

INJECTED = {
    "/usr/local/bin/syncopated-firstboot": "syncopated-firstboot",
    "/usr/local/bin/syncopated-firstboot-launcher": "syncopated-firstboot-launcher",
    "/etc/xdg/autostart/syncopated-firstboot.desktop": "syncopated-firstboot.desktop",
}

out_dir, src_dir, expected = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), int(sys.argv[3])
blueprints = sorted(out_dir.glob("*.toml"))
errors = []
if len(blueprints) != expected:
    errors.append(f"expected {expected} blueprints, found {len(blueprints)}")

for bp in blueprints:
    try:
        doc = tomllib.loads(bp.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"{bp.name}: invalid TOML: {exc}")
        continue
    files = doc.get("customizations", {}).get("files", [])
    for path, src in INJECTED.items():
        hits = [f for f in files if f.get("path") == path]
        if len(hits) != 1:
            errors.append(f"{bp.name}: {path} present {len(hits)} times")
            continue
        want = (src_dir / src).read_bytes()
        if hits[0].get("data", "").encode("utf-8") != want:
            errors.append(f"{bp.name}: {path} data differs from {src}")
    if any("custom-first-boot" in f.get("path", "") for f in files):
        errors.append(f"{bp.name}: still contains a custom-first-boot entry")
    print(f"ok {bp.name}" if not any(e.startswith(bp.name) for e in errors) else f"FAIL {bp.name}")

for e in errors:
    print(f"ERROR {e}")
sys.exit(1 if errors else 0)
