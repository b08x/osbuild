"""Generation-time disk sizing (roles/osbuild/filter_plugins/disk_layout.py).

Each layout is checked at its minimum disk size, a typical size and a large
size, against the role defaults (roles/osbuild/defaults/main.yml): every volume
gets at least its minimum and at most its maximum, fixed volumes get exactly
their size, nothing is over-allocated, and the reserve stays unassigned.
"""
import importlib.util
from pathlib import Path

import pytest
import yaml
from ansible.errors import AnsibleFilterError

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "disk_layout", ROOT / "roles" / "osbuild" / "filter_plugins" / "disk_layout.py")
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)

DEFAULTS = yaml.safe_load((ROOT / "roles" / "osbuild" / "defaults" / "main.yml").read_text())
MIB = 1024


def params(audit_gib=4, tmp="tmpfs", usr_gib=None):
    """The params tasks/disk_layout.yml passes, built from the role defaults."""
    d = {k[len("osbuild_kickstart_"):]: v for k, v in DEFAULTS.items()
         if k.startswith("osbuild_kickstart_") and isinstance(v, int)}
    d["compliant_audit_gib"] = audit_gib
    d["tmp"] = tmp
    if usr_gib:
        d["compliant_usr_gib"] = usr_gib
        d["usr_min_gib"] = max(d["usr_min_gib"], usr_gib)
        d["usr_max_gib"] = max(d["usr_max_gib"], usr_gib)
    return d


def sizes(layout):
    return {v["mount"]: v["size_mib"] for v in layout["volumes"]}


def check_invariants(result, size_gib):
    usable = size_gib * MIB - dl.BUFFER_MIB
    assigned = sum(v["size_mib"] for v in result["volumes"])
    assert result["disk_mib"] == size_gib * MIB
    assert result["usable_mib"] == usable
    assert assigned + result["unassigned_mib"] == usable
    assert result["unassigned_mib"] >= result["reserve_mib"] >= 0
    assert all(v["size_mib"] > 0 for v in result["volumes"])


# ---- simple layout (hardening: none) ----------------------------------------

def test_simple_minimum_disk_fits_all_minimums_and_one_gib_less_does_not():
    p = params()
    minimum = dl.minimum_disk_gib("simple", p)
    result = dl.syncopated_disk_layout(minimum, "simple", p)
    check_invariants(result, minimum)
    s = sizes(result)
    assert s["/"] >= 20 * MIB and s["/usr"] >= 30 * MIB and s["/var"] >= 30 * MIB
    with pytest.raises(AnsibleFilterError, match=f"at least {minimum} GiB"):
        dl.syncopated_disk_layout(minimum - 1, "simple", p)


def test_simple_small_disk_drops_home_and_keeps_the_rest():
    p = params()
    # / 20 + /usr 30 + /var 30 fit, /home's 20 GiB minimum does not.
    result = dl.syncopated_disk_layout(dl.minimum_disk_gib("simple", p) + 5, "simple", p)
    assert "/home" not in sizes(result)


def test_simple_typical_disk_476_gib():
    p = params()
    result = dl.syncopated_disk_layout(476, "simple", p)
    check_invariants(result, 476)
    s = sizes(result)
    assert list(s) == ["/", "/usr", "/var", "/home"]
    # reserve = 8% of usable (472 GiB) = 37.76 GiB, under the 64 GiB cap
    assert result["reserve_mib"] == (476 * MIB - 4096) * 8 // 100
    assert 20 * MIB <= s["/"] <= 64 * MIB
    assert 30 * MIB <= s["/usr"] <= 110 * MIB
    assert 30 * MIB <= s["/var"] <= 110 * MIB
    assert s["/home"] > s["/var"]


def test_simple_large_disk_caps_volumes_and_gives_home_the_rest():
    p = params()
    result = dl.syncopated_disk_layout(4000, "simple", p)
    check_invariants(result, 4000)
    s = sizes(result)
    assert s["/"] == 64 * MIB
    assert s["/usr"] == 110 * MIB
    assert s["/var"] == 110 * MIB
    assert result["reserve_mib"] == 64 * MIB          # capped
    assert result["unassigned_mib"] - result["reserve_mib"] < 4  # rounding only
    assert s["/home"] > 3000 * MIB


def test_simple_cuda_raises_usr_minimum():
    plain = dl.minimum_disk_gib("simple", params())
    cuda = dl.minimum_disk_gib("simple", params(usr_gib=80))
    assert cuda >= plain + 50
    s = sizes(dl.syncopated_disk_layout(476, "simple", params(usr_gib=80)))
    assert s["/usr"] >= 80 * MIB


# Exact sizes the installer %pre allocate() produced before sizing moved to
# generation time (kickstart.bats at v0.5.0): same arithmetic, same results.
def test_simple_matches_the_old_installer_math_nvidia_150_gib():
    s = sizes(dl.syncopated_disk_layout(150, "simple", params(usr_gib=80)))
    assert s == {"/": 21112, "/usr": 83816, "/var": 32616}


@pytest.mark.parametrize("size_gib,expected", [
    (100, {"/": 21697, "/usr": 34371, "/var": 34371}),
    (119, {"/": None, "/usr": 32205, "/var": 32205, "/home": 22955}),
    (233, {"/": 29924, "/usr": 59054, "/var": 59054, "/home": 67703}),
    (477, {"/": 50373, "/usr": 112640, "/var": 112640, "/home": 169950}),
    (931, {"/": 65536, "/usr": 112640, "/var": 112640, "/home": 592896}),
])
def test_simple_matches_the_old_installer_math(size_gib, expected):
    s = sizes(dl.syncopated_disk_layout(size_gib, "simple", params()))
    if size_gib == 119:          # the old test did not pin /
        expected["/"] = s["/"]
    assert s == expected


@pytest.mark.parametrize("size_gib,var,home,unassigned", [
    (477, 122049, 212962, 38749),
    (932, 204800, 569344, 65536),
])
def test_compliant_matches_the_old_installer_math(size_gib, var, home, unassigned):
    result = dl.syncopated_disk_layout(size_gib, "compliant", params(audit_gib=10))
    s = sizes(result)
    assert (s["/var"], s["/home"], result["unassigned_mib"]) == (var, home, unassigned)


# ---- compliant layout (any hardening profile) --------------------------------

FIXED = {"/": 35, "/usr": 45, "/var/tmp": 8, "/var/log": 10}


@pytest.mark.parametrize("audit_gib", [4, 10])
def test_compliant_minimum_disk(audit_gib):
    p = params(audit_gib=audit_gib)
    minimum = dl.minimum_disk_gib("compliant", p)
    result = dl.syncopated_disk_layout(minimum, "compliant", p)
    check_invariants(result, minimum)
    s = sizes(result)
    assert s["/var"] >= 40 * MIB and s["/home"] >= 10 * MIB
    with pytest.raises(AnsibleFilterError, match="too small for the compliant layout"):
        dl.syncopated_disk_layout(minimum - 1, "compliant", p)


@pytest.mark.parametrize("audit_gib", [4, 10])
def test_compliant_typical_disk_476_gib(audit_gib):
    result = dl.syncopated_disk_layout(476, "compliant", params(audit_gib=audit_gib))
    check_invariants(result, 476)
    s = sizes(result)
    for mount, gib in FIXED.items():
        assert s[mount] == gib * MIB, mount
    assert s["/var/log/audit"] == audit_gib * MIB
    assert "/tmp" not in s                      # tmpfs
    assert 40 * MIB <= s["/var"] <= 200 * MIB
    assert s["/home"] > s["/var"]


def test_compliant_large_disk_clamps_var():
    result = dl.syncopated_disk_layout(4000, "compliant", params())
    check_invariants(result, 4000)
    s = sizes(result)
    assert s["/var"] == 200 * MIB
    assert result["reserve_mib"] == 64 * MIB


def test_compliant_tmp_lv_adds_a_fixed_tmp_volume_with_noexec():
    result = dl.syncopated_disk_layout(476, "compliant", params(tmp="lv"))
    tmp = [v for v in result["volumes"] if v["mount"] == "/tmp"]
    assert tmp == [{"mount": "/tmp", "name": "tmp", "size_mib": 8 * MIB, "fsoptions": "nodev,nosuid,noexec"}]


def test_compliant_mount_options():
    opts = {v["mount"]: v["fsoptions"] for v in dl.syncopated_disk_layout(476, "compliant", params())["volumes"]}
    assert opts["/var/log/audit"] == "nodev,nosuid,noexec,noatime"
    assert opts["/var/tmp"] == "nodev,nosuid,noexec,noatime"
    assert opts["/home"] == "nodev,nosuid,noatime"
    assert opts["/usr"] == "nodev,noatime"


def test_compliant_cuda_usr_is_80_gib_and_raises_the_minimum():
    p = params(usr_gib=80)
    assert sizes(dl.syncopated_disk_layout(476, "compliant", p))["/usr"] == 80 * MIB
    assert dl.minimum_disk_gib("compliant", p) == dl.minimum_disk_gib("compliant", params()) + 35 + 3


# ---- argument checks ----------------------------------------------------------

def test_unknown_layout_and_bad_values_are_rejected():
    with pytest.raises(AnsibleFilterError, match="simple or compliant"):
        dl.syncopated_disk_layout(476, "fancy", params())
    with pytest.raises(AnsibleFilterError, match="tmp must be"):
        dl.syncopated_disk_layout(476, "compliant", params(tmp="ramdisk"))
    with pytest.raises(AnsibleFilterError, match="disk.size_gib must be an integer"):
        dl.syncopated_disk_layout("big", "simple", params())
    bad = params()
    bad["root_min_gib"] = 100
    with pytest.raises(AnsibleFilterError, match="larger than root_max_gib"):
        dl.syncopated_disk_layout(476, "simple", bad)


def test_allocate_shares_by_weight_up_to_maximum():
    vols = [{"name": "a", "min": 10, "max": 20, "weight": 1},
            {"name": "b", "min": 10, "max": dl.NO_MAX, "weight": 1}]
    sizes_, left = dl.allocate(100, vols)
    assert sizes_ == {"a": 20, "b": 80} and left == 0
    assert dl.allocate(15, vols) is None
