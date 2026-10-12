"""Unattended QEMU/KVM install of the CIS example ISO (tests/vm/run-install-test.sh).

Build the ISO first, then point the test at it:

    ansible-playbook playbooks/build.yml \
      -e @profiles/examples/rocky-10-2-workstation-openscap-cis-l2-workstation.yml
    bash /var/tmp/osbuild-images/build-rocky-10-2-workstation-openscap-cis-l2-workstation.sh
    SYNCOPATED_VM_ISO=/var/tmp/osbuild-images/rocky-10-2-workstation-openscap-cis-l2-workstation-<commit>.iso \
      python3 -m pytest tests/test_vm_install.py -s

Skipped unless SYNCOPATED_VM_ISO names an ISO and /dev/kvm is usable.
SYNCOPATED_VM_PROFILE selects another (non-LUKS) example intent.
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ISO = os.environ.get("SYNCOPATED_VM_ISO", "")
PROFILE = os.environ.get(
    "SYNCOPATED_VM_PROFILE",
    str(ROOT / "profiles" / "examples" / "rocky-10-2-workstation-openscap-cis-l2-workstation.yml"))


@pytest.mark.skipif(not ISO or not Path(ISO).is_file() or not os.access("/dev/kvm", os.W_OK),
                    reason="set SYNCOPATED_VM_ISO to a built ISO on a host with /dev/kvm")
def test_unattended_install_of_the_cis_example(tmp_path):
    run = subprocess.run(["bash", str(ROOT / "tests" / "vm" / "run-install-test.sh"), ISO, PROFILE,
                          str(tmp_path / "vm")], text=True)
    assert run.returncode == 0
