"""Component lists must reproduce the package sets and blueprints they replaced.

Package parity: the packages rendered from a component list equal the package
set recorded (goals/component-files-only-tracker/baseline/*.pkgs) from each
static workstation TOML that the components replaced.

Snapshot parity: the three Rocky 10 *-components.yml playbooks render the same
blueprint, byte for byte, as before the legacy variables were removed
(baseline/*.toml).
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

_ROCKY10_COMMON = ["base", "anaconda", "gnome-desktop", "fonts", "audio", "multimedia", "google-chrome", "vscode"]

# (stem, components, blueprint name, hostname, description)
SNAPSHOT_CASES = {
    "rocky-iso": (
        "rocky-10-2-workstation-components",
        _ROCKY10_COMMON + ["gui-toolkit", "intel-graphics", "development", "containers-virt", "cockpit", "syncopated"],
        "syncopated-dx", "Rocky Linux Workstation 10.2 (components)"),
    "rocky-iso-nvidia": (
        "rocky-10-2-workstation-nvidia-components",
        _ROCKY10_COMMON + ["intel-graphics", "development", "containers-virt", "cockpit", "nvidia",
                           "cuda-container", "gui-toolkit", "syncopated"],
        "syncopated-dx-nvidia", "Rocky Linux Workstation 10.2 (NVIDIA, components)"),
    "rocky-iso-intel-oneapi": (
        "rocky-10-2-workstation-intel-oneapi-components",
        _ROCKY10_COMMON + ["intel-graphics", "development", "containers-virt", "cockpit", "intel-oneapi", "syncopated"],
        "syncopated-dx-intel",
        "Rocky Linux Workstation 10.2 (Intel oneAPI, components, interactive partitioning)"),
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
    assert rendered == expected, (
        f"missing: {sorted(expected - rendered)}; extra: {sorted(rendered - expected)}")


@pytest.mark.parametrize("case", SNAPSHOT_CASES)
def test_components_playbook_blueprint_is_unchanged(case):
    stem, components, hostname, description = SNAPSHOT_CASES[case]
    rendered = render("rocky-10.2", components, name=stem, hostname=hostname, description=description)
    assert rendered == (BASELINE / f"{stem}.toml").read_text()
