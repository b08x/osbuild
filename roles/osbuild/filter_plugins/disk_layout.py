# SPDX-License-Identifier: MIT-0
"""Generation-time disk layout for the installer kickstart.

tasks/disk_layout.yml calls ``syncopated_disk_layout`` with the declared disk
size (intent ``disk.size_gib``) and the osbuild_kickstart_* sizing variables.
The result holds fixed sizes in MiB for every logical volume; the kickstart
renders them as literal ``logvol --size=`` values, so the installer %pre only
picks the disk and gives a larger-than-declared disk's surplus to /home.

Sizing (the model Anaconda's default_partitioning and systemd-repart use):

1. usable = declared size - BUFFER_MIB (/boot, EFI partition, LVM metadata)
2. reserve = reserve_percent of usable, at most reserve_max_gib; it stays
   unassigned in vg00 so a full volume can be grown with ``lvextend -r``
3. every volume gets its minimum
4. the rest is shared in proportion to the weights until a volume reaches its
   maximum; space no volume can take stays unassigned

Layouts:

* ``simple`` (hardening: none): /, /usr, /var and /home. /home is dropped (a
  directory on /) when the minimums do not fit with it.
* ``compliant`` (any OpenSCAP profile): fixed /, /usr, /var/tmp, /var/log,
  /var/log/audit and (tmp: lv) /tmp, then /var and /home share the rest. Mount
  options are set here because Anaconda writes /etc/fstab at install time,
  after the build-time remediation.
"""

from ansible.errors import AnsibleFilterError

MIB_PER_GIB = 1024
BUFFER_MIB = 4096
NO_MAX = 1 << 50
LARGEST_DISK_GIB = 65536


def allocate(pool, vols):
    """Size ``vols`` (dicts with min, max, weight) within ``pool`` MiB.

    Returns ``(sizes, left)``: sizes by volume name and the MiB no volume took,
    or ``None`` when the minimums alone do not fit.
    """
    size = {v["name"]: v["min"] for v in vols}
    left = pool - sum(v["min"] for v in vols)
    if left < 0:
        return None
    while left > 0:
        open_vols = [v for v in vols if size[v["name"]] < v["max"]]
        total_weight = sum(v["weight"] for v in open_vols)
        if total_weight == 0:
            break
        used = 0
        for v in open_vols:
            add = min(left * v["weight"] // total_weight, v["max"] - size[v["name"]])
            size[v["name"]] += add
            used += add
        if used == 0:
            break
        left -= used
    return size, left


def _gib(value, key):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise AnsibleFilterError(f"{key} must be an integer, got {value!r}")
    if number < 0:
        raise AnsibleFilterError(f"{key} must not be negative, got {number}")
    return number


def _volume(mount, name, gib_min, gib_max, weight, fsoptions):
    return {
        "mount": mount,
        "name": name,
        "min": gib_min * MIB_PER_GIB,
        "max": NO_MAX if gib_max is None else gib_max * MIB_PER_GIB,
        "weight": weight,
        "fsoptions": fsoptions,
    }


def _fixed(mount, name, gib, fsoptions):
    return _volume(mount, name, gib, gib, 0, fsoptions)


def _volumes(layout, p):
    """Volume requests for a layout; ``p`` maps parameter names to integers."""
    if layout == "compliant":
        vols = [
            _fixed("/", "root", p["compliant_root_gib"], "noatime"),
            _fixed("/usr", "usr", p["compliant_usr_gib"], "nodev,noatime"),
            _volume("/var", "var", p["compliant_var_min_gib"], p["compliant_var_max_gib"],
                    p["compliant_var_weight"], "nodev,nosuid,noatime"),
            _fixed("/var/tmp", "var_tmp", p["compliant_var_tmp_gib"], "nodev,nosuid,noexec,noatime"),
            _fixed("/var/log", "var_log", p["compliant_var_log_gib"], "nodev,nosuid,noexec,noatime"),
            _fixed("/var/log/audit", "var_log_audit", p["compliant_audit_gib"], "nodev,nosuid,noexec,noatime"),
        ]
        if p["tmp"] == "lv":
            vols.append(_fixed("/tmp", "tmp", p["compliant_tmp_gib"], "nodev,nosuid,noexec"))
        vols.append(_volume("/home", "home", p["compliant_home_min_gib"], None,
                            p["compliant_home_weight"], "nodev,nosuid,noatime"))
        return vols, p["compliant_reserve_percent"]
    vols = [
        _volume("/", "root", p["root_min_gib"], p["root_max_gib"], p["root_weight"], ""),
        _volume("/usr", "usr", p["usr_min_gib"], p["usr_max_gib"], p["usr_weight"], ""),
        _volume("/var", "var", p["var_min_gib"], p["var_max_gib"], p["var_weight"], ""),
        _volume("/home", "home", p["home_min_gib"], None, p["home_weight"], ""),
    ]
    return vols, p["reserve_percent"]


def _try(size_gib, layout, p):
    """Layout for ``size_gib`` or ``None`` when the minimums do not fit."""
    vols, reserve_percent = _volumes(layout, p)
    usable = size_gib * MIB_PER_GIB - BUFFER_MIB
    if usable <= 0:
        return None
    reserve = min(usable * reserve_percent // 100, p["reserve_max_gib"] * MIB_PER_GIB)
    pool = usable - reserve
    result = allocate(pool, vols)
    if result is None and layout == "simple":
        # /home is optional in the simple layout: it becomes a directory on /.
        vols = [v for v in vols if v["name"] != "home"]
        result = allocate(pool, vols)
    if result is None:
        return None
    sizes, left = result
    return {
        "layout": layout,
        "disk_mib": size_gib * MIB_PER_GIB,
        "usable_mib": usable,
        "reserve_mib": reserve,
        "unassigned_mib": reserve + left,
        "volumes": [
            {"mount": v["mount"], "name": v["name"], "size_mib": sizes[v["name"]],
             "fsoptions": v["fsoptions"]}
            for v in vols
        ],
    }


def minimum_disk_gib(layout, params):
    """Smallest whole GiB disk the layout fits on."""
    p = _params(layout, params)
    for size in range(1, LARGEST_DISK_GIB + 1):
        if _try(size, layout, p) is not None:
            return size
    raise AnsibleFilterError(f"the {layout} layout does not fit on any disk up to {LARGEST_DISK_GIB} GiB")


_INT_KEYS = {
    "simple": ["reserve_percent", "reserve_max_gib",
               "root_min_gib", "root_max_gib", "root_weight",
               "usr_min_gib", "usr_max_gib", "usr_weight",
               "var_min_gib", "var_max_gib", "var_weight",
               "home_min_gib", "home_weight"],
    "compliant": ["compliant_reserve_percent", "reserve_max_gib",
                  "compliant_root_gib", "compliant_usr_gib", "compliant_tmp_gib",
                  "compliant_var_tmp_gib", "compliant_var_log_gib", "compliant_audit_gib",
                  "compliant_var_min_gib", "compliant_var_max_gib", "compliant_var_weight",
                  "compliant_home_min_gib", "compliant_home_weight"],
}


def _params(layout, params):
    if layout not in _INT_KEYS:
        raise AnsibleFilterError(f"layout must be simple or compliant, got {layout!r}")
    missing = [k for k in _INT_KEYS[layout] if k not in params]
    if missing:
        raise AnsibleFilterError(f"disk layout parameters missing: {', '.join(missing)}")
    p = {k: _gib(params[k], k) for k in _INT_KEYS[layout]}
    p["tmp"] = params.get("tmp", "tmpfs")
    if p["tmp"] not in ("tmpfs", "lv"):
        raise AnsibleFilterError(f"tmp must be tmpfs or lv, got {p['tmp']!r}")
    pct = p["compliant_reserve_percent" if layout == "compliant" else "reserve_percent"]
    if pct >= 100:
        raise AnsibleFilterError(f"reserve percent must be below 100, got {pct}")
    for name in ("root", "usr", "var"):
        lo, hi = (f"compliant_{name}_min_gib", f"compliant_{name}_max_gib") if layout == "compliant" \
            else (f"{name}_min_gib", f"{name}_max_gib")
        if lo in p and hi in p and p[lo] > p[hi]:
            raise AnsibleFilterError(f"{lo} ({p[lo]}) is larger than {hi} ({p[hi]})")
    return p


def syncopated_disk_layout(size_gib, layout, params):
    """Fixed volume sizes for a disk of ``size_gib`` GiB.

    Raises AnsibleFilterError naming the minimum disk size when the layout does
    not fit.
    """
    size = _gib(size_gib, "disk.size_gib")
    p = _params(layout, params)
    result = _try(size, layout, p)
    if result is None:
        raise AnsibleFilterError(
            f"disk.size_gib={size} is too small for the {layout} layout; "
            f"it needs at least {minimum_disk_gib(layout, params)} GiB")
    result["minimum_disk_gib"] = minimum_disk_gib(layout, params)
    return result


class FilterModule:
    def filters(self):
        return {
            "syncopated_disk_layout": syncopated_disk_layout,
            "syncopated_minimum_disk_gib": minimum_disk_gib,
        }
