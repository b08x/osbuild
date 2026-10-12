"""image-builder manifest depsolve for every example intent.

Runs `image-builder manifest` with the generated blueprint and the same
--extra-repo list the build script uses, then reads the manifest:

* every hardened example has the org.osbuild.oscap.autotailor stage (the
  workstation tailoring) and org.osbuild.oscap.remediation using its
  tailored profile, and the autotailor stage unselects the audit rules;
* the installer kickstart in the manifest's inline sources passes
  `ksvalidator -v RHEL10` (with the layout filled in for a disk).

Needs image-builder (and network access to the repositories) on the host,
i.e. a Fedora or EL 10 build host such as gir; skipped elsewhere.
SYNCOPATED_MANIFEST_TESTS=0 skips it on a build host too.
"""
import base64
import json
import os
import re
import shutil
import subprocess

import pytest

from intent_helpers import EXAMPLES, load_intent

IMAGE_BUILDER = shutil.which("image-builder")
pytestmark = pytest.mark.skipif(
    not IMAGE_BUILDER or os.environ.get("SYNCOPATED_MANIFEST_TESTS") == "0",
    reason="image-builder not installed (run on a Fedora/EL 10 build host)")


def manifest(g, tmp_path):
    intent = load_intent(next(p for p in EXAMPLES if p.stem == g.name))
    image_type = "minimal-installer" if intent["distro"].startswith("fedora-") else "image-installer"
    cmd = [IMAGE_BUILDER, "manifest", image_type, "--distro", intent["distro"], "--arch", intent["arch"],
           "--blueprint", str(g.toml_path)]
    for url in g.report["extra_repo_urls"]:
        cmd += ["--extra-repo", url]
    run = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_path, timeout=1800)
    assert run.returncode == 0, run.stderr[-4000:]
    return json.loads(run.stdout)


def stages(doc):
    return [s for p in doc["pipelines"] for s in p.get("stages", [])]


@pytest.mark.parametrize("example", [p.stem for p in EXAMPLES])
def test_example_depsolves_and_carries_the_tailoring(generated, example, tmp_path):
    g = generated[example]
    doc = manifest(g, tmp_path)
    types = [s["type"] for s in stages(doc)]
    if load_intent(next(p for p in EXAMPLES if p.stem == example))["hardening"] == "none":
        assert "org.osbuild.oscap.remediation" not in types
    else:
        assert "org.osbuild.oscap.autotailor" in types
        assert "org.osbuild.oscap.remediation" in types
        tailor = next(s for s in stages(doc) if s["type"] == "org.osbuild.oscap.autotailor")
        path = g.customizations["openscap"]["json_tailoring"]["filepath"]
        assert tailor["options"]["config"]["tailoring_file"] == path
        assert {"auditd_data_retention_max_log_file_action"} <= set(g.unselected())
        remediation = next(s for s in stages(doc) if s["type"] == "org.osbuild.oscap.remediation")
        assert "tailoring" in json.dumps(remediation)

    ksvalidator = shutil.which("ksvalidator")
    if ksvalidator:
        inline = doc.get("sources", {}).get("org.osbuild.inline", {}).get("items", {})
        kickstarts = [base64.b64decode(i["data"]).decode() for i in inline.values()
                      if i.get("encoding") == "base64" and "syncopated-layout.ks" in base64.b64decode(i["data"]).decode(errors="replace")]
        assert kickstarts, "no kickstart with the Syncopated layout in the manifest"
        layout = re.search(r"cat >/tmp/syncopated-layout\.ks <<'EOF'\n(.*?)\nEOF\n", kickstarts[0], re.S).group(1)
        ks = tmp_path / "ks.cfg"
        ks.write_text(kickstarts[0].replace("%include /tmp/partitions.ks\n", layout.replace("@DISK@", "vda") + "\n"))
        run = subprocess.run([ksvalidator, "-v", "RHEL10", str(ks)], capture_output=True, text=True)
        assert run.returncode == 0, run.stdout
