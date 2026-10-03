#!/usr/bin/env python3
"""Check prepared blueprints for the injected installer kickstart.

Usage: check_kickstart.py OUTPUT_DIR KS_SRC EXPECTED_COUNT MODE LOCALE KEYBOARD TIMEZONE [KSVALIDATOR]

MODE is "enabled" or "disabled" (osbuild_kickstart_enabled). Every
OUTPUT_DIR/*.toml must parse as TOML and carry no user, group, unattended or
sudo-nopasswd setting, must enable the Anaconda Users module, and must ship
the wheel sudoers drop-in, the Flathub remote file and /etc/syncopated-release
(naming the blueprint) exactly once. With MODE=enabled the kickstart
contents must be the rendered lang/keyboard/timezone lines, the layout %pre
that writes /tmp/syncopated-layout.env (exactly the LAYOUT_KEYS, integer
values), then KS_SRC byte for byte; with MODE=disabled there must be no kickstart at all. When
KSVALIDATOR is given, each rendered kickstart is also run through it.
"""
import pathlib
import re
import subprocess
import sys
import tempfile
import tomllib

USERS_MODULE = "org.fedoraproject.Anaconda.Modules.Users"
SUDOERS = "/etc/sudoers.d/90-wheel-nopasswd"
FLATHUB = "/etc/flatpak/remotes.d/flathub.flatpakrepo"
RELEASE = "/etc/syncopated-release"

out_dir, ks_src = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
expected, mode = int(sys.argv[3]), sys.argv[4]
locale, keyboard, timezone = sys.argv[5:8]
ksvalidator = sys.argv[8] if len(sys.argv) > 8 else ""
header = f"lang {locale}\nkeyboard {keyboard}\ntimezone {timezone} --utc\n"
want = header + ks_src.read_text(encoding="utf-8")
flathub_src = (ks_src.parent.parent / "flatpak" / "flathub.flatpakrepo").read_text(encoding="utf-8")
LAYOUT_KEYS = ["MIN_MIB", "ROOT_PCT", "ROOT_MIN_MIB", "RESERVE_PCT", "USR_PCT",
               "USR_MAX_MIB", "VAR_MAX_MIB", "HOME_MIN_MIB"]
LAYOUT_RE = re.compile(
    r"%pre --interpreter=/usr/bin/bash --erroronfail\n"
    r"cat >/tmp/syncopated-layout\.env <<'EOF'\n((?:[A-Z_]+=[0-9]+\n)+)EOF\n%end\n")


def strip_layout(contents):
    """Return contents without the layout %pre, or an error string."""
    if not contents.startswith(header):
        return None, "kickstart does not start with the lang/keyboard/timezone header"
    m = LAYOUT_RE.match(contents, len(header))
    if not m:
        return None, "layout %pre missing after the header"
    keys = [line.split("=")[0] for line in m.group(1).splitlines()]
    if keys != LAYOUT_KEYS:
        return None, f"layout keys {keys} != {LAYOUT_KEYS}"
    return header + contents[m.end():], None

blueprints = sorted(out_dir.glob("*.toml"))
errors = []
if len(blueprints) != expected:
    errors.append(f"expected {expected} blueprints, found {len(blueprints)}")

for bp in blueprints:
    raw = bp.read_text(encoding="utf-8")
    try:
        doc = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"{bp.name}: invalid TOML: {exc}")
        print(f"FAIL {bp.name}")
        continue
    err = []
    cust = doc.get("customizations", {})
    inst = cust.get("installer", {})
    for key in ("user", "group"):
        if key in cust:
            err.append(f"has [[customizations.{key}]]")
    for key in ("unattended", "sudo-nopasswd"):
        if key in inst:
            err.append(f"has installer.{key}")
    if USERS_MODULE not in inst.get("modules", {}).get("enable", []):
        err.append("does not enable the Anaconda Users module")

    sudoers = [f for f in cust.get("files", []) if f.get("path") == SUDOERS]
    if len(sudoers) != 1:
        err.append(f"{SUDOERS} present {len(sudoers)} times")
    elif sudoers[0].get("mode") != "0440" or sudoers[0].get("data") != "%wheel ALL=(ALL) NOPASSWD: ALL\n":
        err.append(f"{SUDOERS} has wrong mode or data")

    flathub = [f for f in cust.get("files", []) if f.get("path") == FLATHUB]
    if len(flathub) != 1:
        err.append(f"{FLATHUB} present {len(flathub)} times")
    elif flathub[0].get("mode") != "0644" or flathub[0].get("data") != flathub_src:
        err.append(f"{FLATHUB} has wrong mode or differs from files/flatpak/flathub.flatpakrepo")

    release = [f for f in cust.get("files", []) if f.get("path") == RELEASE]
    if len(release) != 1:
        err.append(f"{RELEASE} present {len(release)} times")
    elif f"SYNCOPATED_BLUEPRINT={bp.stem}\n" not in release[0].get("data", ""):
        err.append(f"{RELEASE} does not name blueprint {bp.stem}")

    markers = raw.count("# BEGIN syncopated-kickstart")
    contents = inst.get("kickstart", {}).get("contents")
    if mode == "enabled":
        if markers != 1:
            err.append(f"kickstart block present {markers} times")
        stripped, layout_err = strip_layout(contents or "")
        if layout_err:
            err.append(layout_err)
        elif stripped != want:
            err.append("kickstart contents differ from rendered header + layout + source")
        elif ksvalidator:
            with tempfile.NamedTemporaryFile("w", suffix=".ks") as ks:
                ks.write(contents.replace("%include /tmp/partitions.ks\n", ""))
                ks.flush()
                run = subprocess.run([ksvalidator, ks.name], capture_output=True, text=True)
                if run.returncode != 0:
                    err.append(f"ksvalidator: {run.stdout.strip()} {run.stderr.strip()}")
    else:
        if markers or contents is not None:
            err.append("kickstart present although disabled")

    errors.extend(f"{bp.name}: {e}" for e in err)
    print(f"FAIL {bp.name}" if err else f"ok {bp.name}")

for e in errors:
    print(f"ERROR {e}")
sys.exit(1 if errors else 0)
