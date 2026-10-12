"""Each example intent reproduces the blueprint its retired ISO playbook made.

goals/standalone-workstation-hardening/baseline/<name>.toml was rendered from
the ISO playbooks before they were deleted (same role tasks, commit stamped
BASELINE). The blueprint an example intent generates must equal it after
removing only the intended changes:

* the installer kickstart (unattended users, generation-time disk layout)
* the workstation audit policy files and the OpenSCAP tailoring
* systemd-journal-upload disabled and the audit check timer enabled
* the oneAPI description, which no longer mentions interactive partitioning
"""
import copy
import re
import tomllib

import pytest

from intent_helpers import EXAMPLES, ROOT

BASELINE = ROOT / "goals" / "standalone-workstation-hardening" / "baseline"
HARDENING_PATHS = {
    "/etc/audit/auditd.conf", "/etc/syncopated/audit-warn.conf", "/usr/local/sbin/syncopated-audit-warn",
    "/usr/local/bin/syncopated-audit-notify", "/etc/xdg/autostart/syncopated-audit-notify.desktop",
    "/etc/systemd/system/syncopated-audit-check.service", "/etc/systemd/system/syncopated-audit-check.timer",
    "/usr/local/bin/syncopated-scan", "/etc/syncopated/scan.conf", "/etc/cockpit/cockpit.conf",
}
DESCRIPTION_CHANGES = {
    "rocky-10-2-workstation-intel-oneapi-components":
        ("Rocky Linux Workstation 10.2 (Intel oneAPI, components, interactive partitioning)",
         "Rocky Linux Workstation 10.2 (Intel oneAPI, components)"),
}


def comparable(doc, name, side):
    doc = copy.deepcopy(doc)
    cust = doc["customizations"]
    cust["installer"].pop("kickstart", None)
    cust.get("openscap", {}).pop("tailoring", None)
    cust["files"] = [f for f in cust["files"] if f["path"] not in HARDENING_PATHS]
    for f in cust["files"]:
        if f["path"] == "/etc/syncopated-release":
            f["data"] = re.sub(r"SYNCOPATED_COMMIT=.*", "SYNCOPATED_COMMIT=*", f["data"])
    services = cust.get("services", {})
    services.pop("disabled", None)
    services["enabled"] = [s for s in services.get("enabled", []) if s != "syncopated-audit-check.timer"]
    if side == "baseline" and name in DESCRIPTION_CHANGES:
        old, new = DESCRIPTION_CHANGES[name]
        assert doc["description"] == old
        doc["description"] = new
    return doc


def test_every_example_has_a_baseline():
    assert sorted(p.stem for p in EXAMPLES) == sorted(p.stem for p in BASELINE.glob("*.toml"))


@pytest.mark.parametrize("name", [p.stem for p in EXAMPLES])
def test_blueprint_matches_the_retired_playbook(generated, name):
    new = comparable(generated[name].blueprint, name, "new")
    old = comparable(tomllib.loads((BASELINE / f"{name}.toml").read_text()), name, "baseline")
    assert new.keys() == old.keys()
    for key in old:
        if key == "customizations":
            for sub in old[key]:
                assert new[key].get(sub) == old[key][sub], f"customizations.{sub} differs"
            assert new[key].keys() == old[key].keys()
        else:
            assert new[key] == old[key], f"{key} differs"


@pytest.mark.parametrize("name", [p.stem for p in EXAMPLES])
def test_appended_blocks_keep_their_order(generated, name):
    markers = re.findall(r"^# BEGIN (\S+)", generated[name].raw, re.M)
    old = re.findall(r"^# BEGIN (\S+)", (BASELINE / f"{name}.toml").read_text(), re.M)
    assert [m for m in markers if m != "syncopated-hardening"] == old
