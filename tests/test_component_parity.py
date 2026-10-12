"""Component lists must reproduce the package sets and blueprints they replaced.

Package parity: the packages rendered from a component list equal the package
set recorded (goals/component-files-only-tracker/baseline/*.pkgs) from each
static workstation TOML that the components replaced.

Packages added on purpose after the baseline was recorded are listed in
ADDED_SINCE_BASELINE with the commit that added them.

The blueprint snapshots of the retired Rocky 10 ISO playbooks live on in
tests/test_intent_parity.py, which compares each example intent with the
blueprint its playbook made.
"""
from pathlib import Path

import pytest

from blueprint_packages import package_names
from render import render

BASELINE = Path(__file__).resolve().parent.parent / "goals" / "component-files-only-tracker" / "baseline"

BASE_LIST = ["base", "anaconda", "gnome-desktop", "fonts", "audio", "multimedia",
             "google-chrome", "vscode", "intel-graphics", "development",
             "containers-virt", "cockpit"]

# (render distro, component list, baseline package-set stem)
PACKAGE_CASES = {
    "alma10-plain": ("almalinux-10.2", BASE_LIST + ["syncopated"], "almalinux-10-2-workstation"),
    "alma10-nvidia": ("almalinux-10.2", BASE_LIST + ["nvidia", "syncopated"], "almalinux-10-2-workstation-nvidia"),
    "rocky9-plain": ("rocky-9.8", BASE_LIST, "rocky-9-8-workstation"),
    "rocky9-nvidia": ("rocky-9.8", BASE_LIST + ["nvidia"], "rocky-9-8-workstation-nvidia"),
    "fedora43-plain": ("fedora-43", BASE_LIST + ["sway"], "fedora-workstation-43"),
    "fedora43-nvidia": ("fedora-43", BASE_LIST + ["sway", "nvidia"], "fedora-workstation-43-nvidia"),
    "rocky10-cuda-container": ("rocky-10.2", ["cuda-container"], "rocky-10-2-cuda-container"),
}

# Added to components after baseline/*.pkgs was recorded.
#   82c4e7a  lld in every target's base component
#   b123a31  JupyterLab in the EL 10 development component
ADDED_SINCE_BASELINE = {
    "almalinux-10.2": {"lld", "jupyterlab", "python3-ipykernel", "python3-jupyter-core",
                       "python3-jupyter-events", "python3-jupyter-server", "python3-jupyterlab-server",
                       "python3-jupyterlab_pygments", "python3-nbconvert"},
    "rocky-9.8": {"lld"},
    "fedora-43": {"lld"},
    "rocky-10.2": set(),
}


@pytest.mark.parametrize("case", PACKAGE_CASES)
def test_package_set_equals_static_blueprint(case):
    distro, components, stem = PACKAGE_CASES[case]
    rendered = set(package_names(render(distro, components)))
    expected = set((BASELINE / f"{stem}.pkgs").read_text().split())
    if "syncopated" in components:
        # Packages added after the baseline was recorded, plus those moved in
        # from base/fonts (input-remapper, yaru-theme), which the baseline has.
        expected |= set(package_names(render(distro, ["syncopated"])))
    expected |= ADDED_SINCE_BASELINE[distro]
    assert rendered == expected, (
        f"missing: {sorted(expected - rendered)}; extra: {sorted(rendered - expected)}")
