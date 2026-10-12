"""The workstation tailoring against real SCAP content and tools.

Needs oscap, autotailor and a scap-security-guide data stream. The images
use ssg-rhel10-ds.xml; where only ssg-rhel9-ds.xml is installed (e.g.
Debian/Ubuntu ssg-nondebian) the rule IDs are checked against it, allowing
the rules that RHEL 10 content added. Skipped when no data stream exists.
"""
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "roles" / "osbuild" / "files" / "scripts" / "syncopated-scan.sh"
COMPONENTS = ROOT / "roles" / "osbuild" / "files" / "rocky" / "10" / "x86_64" / "components"
CONTENT = Path("/usr/share/xml/scap/ssg/content")
DATASTREAM = next((CONTENT / f for f in ("ssg-rhel10-ds.xml", "ssg-rhel9-ds.xml") if (CONTENT / f).is_file()), None)
XCCDF = "{http://checklists.nist.gov/xccdf/1.2}"
RULE = "xccdf_org.ssgproject.content_rule_"
# Unselected for CIS on RHEL 10 only (tasks/hardening.yml, remote logging off).
RHEL10_ONLY = {"service_systemd-journal-upload_enabled"}

needs_content = pytest.mark.skipif(DATASTREAM is None, reason="no ssg-rhel10/9 data stream installed")


def unselected(profile):
    return yaml.safe_load((COMPONENTS / f"openscap-{profile}.yml").read_text())["openscap_unselected"]


@pytest.fixture(scope="module")
def benchmark():
    tree = ET.parse(DATASTREAM)
    rules = {r.get("id")[len(RULE):] for r in tree.iter(XCCDF + "Rule")}
    profiles = {}
    for p in tree.iter(XCCDF + "Profile"):
        profiles[p.get("id").split("_profile_")[1]] = {
            s.get("idref")[len(RULE):] for s in p.findall(XCCDF + "select") if s.get("selected") == "true"}
    return rules, profiles


@needs_content
@pytest.mark.parametrize("profile", ["cis-l2-workstation", "pci-dss", "hipaa"])
def test_every_unselected_rule_exists(benchmark, profile):
    rules, _ = benchmark
    missing = set(unselected(profile)) - rules
    if DATASTREAM.name == "ssg-rhel9-ds.xml":
        missing -= RHEL10_ONLY
    assert not missing


@needs_content
@pytest.mark.parametrize("profile,stock", [("cis-l2-workstation", "cis_workstation_l2"), ("pci-dss", "pci-dss"),
                                           ("hipaa", "hipaa")])
def test_tailoring_removes_every_selected_halt_or_retention_rule(benchmark, profile, stock):
    _, profiles = benchmark
    selected = profiles[stock] - set(unselected(profile))
    left = {r for r in selected if r.startswith("auditd_data_") and re.search(
        r"_action(_stig)?$|max_log_file|num_logs|space_left", r)}
    assert not left, f"{stock} still selects {left}"
    if profile == "hipaa":
        assert {r for r in profiles[stock] if r.startswith("audit_rules_")} <= selected
    else:
        assert not {r for r in selected if r.startswith(("audit_rules_dac_modification_",
                                                          "audit_rules_file_deletion_events_"))}


@needs_content
@pytest.mark.skipif(not (shutil.which("oscap") and shutil.which("autotailor")), reason="oscap/autotailor missing")
def test_syncopated_scan_reports_tailored_rules_as_not_selected(tmp_path):
    rules = unselected("cis-l2-workstation")
    tailoring = tmp_path / "tailoring.json"
    tailoring.write_text(json.dumps({"profiles": [{
        "id": "cis_workstation_l2_syncopated", "base_profile_id": "cis_workstation_l2",
        "rules": {r: {"evaluate": False} for r in rules},
        "variables": {"var_password_pam_minlen": {"value": "9"}}}]}))
    conf = tmp_path / "scan.conf"
    conf.write_text(
        f"DATASTREAM={DATASTREAM}\n"
        "PROFILE=xccdf_org.ssgproject.content_profile_cis_workstation_l2\n"
        f'TAILORING_FILES="{tmp_path}/none.xml"\n'
        f"TAILORING_JSON={tailoring}\n")
    run = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "SYNC_SCAN_CONF": str(conf),
                              "SYNC_SCAN_DIR": str(tmp_path / "scans")}, timeout=900)
    assert run.returncode == 0, run.stderr
    (out,) = (tmp_path / "scans").iterdir()
    for name in ("stock-arf.xml", "stock-report.html", "tailored-arf.xml", "tailored-report.html",
                 "tailoring.xml", "summary.txt"):
        assert (out / name).is_file(), name
    assert oct((out).stat().st_mode & 0o777) == "0o700"

    def result(arf, rule):
        m = re.search(rf'<rule-result[^>]*idref="{RULE}{rule}"[^>]*>.*?<result>(\w+)</result>',
                      (out / arf).read_text(), re.S)
        return m.group(1) if m else None

    for rule in ("audit_rules_dac_modification_chmod", "auditd_data_retention_max_log_file_action",
                 "auditd_data_retention_admin_space_left_action"):
        assert result("tailored-arf.xml", rule) == "notselected", rule
        assert result("stock-arf.xml", rule) != "notselected", rule


def test_scan_without_a_data_stream_fails_cleanly(tmp_path):
    conf = tmp_path / "scan.conf"
    conf.write_text("DATASTREAM=/nonexistent.xml\nPROFILE=x\n")
    run = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "SYNC_SCAN_CONF": str(conf)})
    assert run.returncode == 1
    assert "data stream /nonexistent.xml not found" in run.stderr
