#!/usr/bin/env bash
# Unattended install test: install an ISO generated from an intent into a
# QEMU/KVM VM with no input, then check the installed system.
#
#   tests/vm/run-install-test.sh ISO PROFILE [WORKDIR]
#
#   ISO      built by build-<name>.sh, e.g.
#            /var/tmp/osbuild-images/rocky-10-2-workstation-openscap-cis-l2-workstation-<commit>.iso
#   PROFILE  the intent it was built from (disk.size_gib and hardening are
#            read from it), e.g. profiles/examples/rocky-10-2-workstation-openscap-cis-l2-workstation.yml
#   WORKDIR  scratch directory (default: a new one under /var/tmp)
#
# Stages, each failing the run with a message:
#   1. install  UEFI VM with a disk of exactly disk.size_gib, the ISO as CD;
#               nothing is typed: the 30 s countdown expires and Anaconda
#               installs. The kickstart's reboot ends QEMU (-no-reboot).
#               INSTALL_TIMEOUT (s, default 7200) bounds it.
#   2. offline  libguestfs reads the disk: the vg00 volumes and their sizes
#               match the generated layout, /var/log/audit is a separate
#               nodev,nosuid,noexec volume, auditd.conf rotates and never
#               halts, root is locked, the user exists with an expired
#               password.
#   3. online   a one-shot unit (virt-customize, SELinux relabelled) runs
#               syncopated-scan, records `auditctl -s`, the failed units and
#               `systemctl is-system-running`, and powers off. The reports
#               are copied out and checked: stock and tailored ARF/HTML
#               exist and the tailored ARF lists the unselected rules as
#               notselected.
#
# Needs: qemu-system-x86_64 with /dev/kvm, OVMF (edk2-ovmf), qemu-img,
# libguestfs-tools (guestfish, virt-customize, virt-copy-out), python3 with
# PyYAML. Runs as a user that may use /dev/kvm; libguestfs needs a kernel it
# can read (LIBGUESTFS_BACKEND=direct is set).
set -euo pipefail

ISO=${1:?usage: run-install-test.sh ISO PROFILE [WORKDIR]}
PROFILE=${2:?usage: run-install-test.sh ISO PROFILE [WORKDIR]}
WORK=${3:-$(mktemp -d /var/tmp/syncopated-vmtest.XXXXXX)}
INSTALL_TIMEOUT=${INSTALL_TIMEOUT:-7200}
BOOT_TIMEOUT=${BOOT_TIMEOUT:-2400}
MEM=${MEM:-8192}
CPUS=${CPUS:-4}
export LIBGUESTFS_BACKEND=direct

fail() {
  echo "FAIL: $*" >&2
  exit 1
}
step() {
  echo "==> $*"
}

for tool in qemu-system-x86_64 qemu-img guestfish virt-customize virt-copy-out python3; do
  command -v "$tool" >/dev/null || fail "$tool not found"
done
[ -w /dev/kvm ] || fail "/dev/kvm is not usable by $(id -un)"
[ -r "$ISO" ] || fail "ISO $ISO not readable"

ovmf_code=
for f in /usr/share/edk2/ovmf/OVMF_CODE.fd /usr/share/OVMF/OVMF_CODE.fd /usr/share/OVMF/OVMF_CODE_4M.fd; do
  [ -r "$f" ] && ovmf_code=$f && break
done
[ -n "$ovmf_code" ] || fail "OVMF firmware not found (install edk2-ovmf)"
ovmf_vars=${ovmf_code/CODE/VARS}

read -r SIZE_GIB HARDENING USER_NAME < <(python3 -c '
import sys, yaml
i = yaml.safe_load(open(sys.argv[1]))["intent"]
print(i["disk"]["size_gib"], i["hardening"], i["users"][0]["name"])' "$PROFILE")
[ "$(python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["intent"]["disk"].get("encrypt", False))' "$PROFILE")" = False ] ||
  fail "the profile sets disk.encrypt; the unattended test needs a profile without LUKS (the passphrase prompt)"

mkdir -p "$WORK"
DISK=$WORK/disk.qcow2
cp "$ovmf_vars" "$WORK/OVMF_VARS.fd"
# Exactly the declared size: the %pre accepts it and no surplus goes to /home.
qemu-img create -q -f qcow2 "$DISK" "${SIZE_GIB}G"

qemu() {
  qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m "$MEM" -smp "$CPUS" \
    -drive if=pflash,format=raw,readonly=on,file="$ovmf_code" \
    -drive if=pflash,format=raw,file="$WORK/OVMF_VARS.fd" \
    -drive file="$DISK",if=none,id=disk0,format=qcow2 \
    -device nvme,drive=disk0,serial=SYNCVMTEST0001 \
    -netdev user,id=net0 -device virtio-net-pci,netdev=net0 \
    -display none -vga std -no-reboot "$@"
}

# ---- 1. install ---------------------------------------------------------------
step "installing $ISO onto a ${SIZE_GIB} GiB NVMe disk (timeout ${INSTALL_TIMEOUT}s, no input)"
start=$(date +%s)
if ! timeout "$INSTALL_TIMEOUT" bash -c "$(declare -f qemu); MEM=$MEM CPUS=$CPUS WORK=$WORK DISK=$DISK ovmf_code=$ovmf_code qemu \
  -cdrom '$ISO' -boot order=d,once=d -serial file:'$WORK/install-serial.log'"; then
  fail "the install did not finish within ${INSTALL_TIMEOUT}s (a prompt or an aborted %pre waits forever); see $WORK/install-serial.log"
fi
echo "    installed in $(($(date +%s) - start)) s"

# ---- 2. offline checks -------------------------------------------------------------
step "checking the installed disk offline"
guestfish --ro -a "$DISK" -i <<'EOF' >"$WORK/offline.txt" 2>&1 || fail "guestfish could not inspect the disk; see $WORK/offline.txt"
echo ---lvs
lvs-full
echo ---fstab
cat /etc/fstab
echo ---auditd
cat /etc/audit/auditd.conf
echo ---shadow
cat /etc/shadow
echo ---release
cat /etc/syncopated-release
EOF

python3 - "$WORK/offline.txt" "$HARDENING" "$USER_NAME" <<'PY' || fail "offline checks failed (details above; raw data in $WORK/offline.txt)"
import re, sys
text, hardening, user = open(sys.argv[1]).read(), sys.argv[2], sys.argv[3]
sections = dict(re.findall(r"^---(\w+)\n(.*?)(?=^---|\Z)", text, re.S | re.M))
errors = []
lvs = {m.group(1): int(m.group(2)) for m in re.finditer(r"lv_name: (\S+)\n(?:.*\n)*?lv_size: (\d+)", sections["lvs"])}
want = {"root", "usr", "var", "home"}
if hardening != "none":
    want |= {"var_tmp", "var_log", "var_log_audit"}
if not want <= set(lvs):
    errors.append(f"volumes {sorted(lvs)} lack {sorted(want - set(lvs))}")
if hardening != "none":
    audit_gib = 10 if hardening == "hipaa" else 4
    if lvs.get("var_log_audit") != audit_gib * 1024 ** 3:
        errors.append(f"/var/log/audit is {lvs.get('var_log_audit')} bytes, want {audit_gib} GiB")
    line = next((l for l in sections["fstab"].splitlines() if re.search(r"\s/var/log/audit\s", l)), "")
    for opt in ("nodev", "nosuid", "noexec"):
        if opt not in line:
            errors.append(f"/var/log/audit fstab line lacks {opt}: {line!r}")
    conf = dict(map(str.strip, l.split("=", 1)) for l in sections["auditd"].splitlines() if "=" in l and not l.startswith("#"))
    for key, value in {"max_log_file_action": "rotate", "admin_space_left_action": "rotate",
                       "disk_full_action": "rotate", "disk_error_action": "syslog"}.items():
        if conf.get(key, "").lower() != value:
            errors.append(f"auditd.conf {key} = {conf.get(key)!r}, want {value}")
    for key in ("space_left_action", "admin_space_left_action", "disk_full_action", "disk_error_action"):
        if re.search(r"single|halt|suspend", conf.get(key, ""), re.I):
            errors.append(f"auditd.conf {key} = {conf.get(key)!r} can halt the system")
shadow = {l.split(":")[0]: l.split(":") for l in sections["shadow"].splitlines() if ":" in l}
if not shadow.get("root", ["", ""])[1].startswith(("!", "*")):
    errors.append("root is not locked")
if user not in shadow:
    errors.append(f"user {user} was not created")
elif shadow[user][2] != "0":
    errors.append(f"user {user} password is not expired (lastchg {shadow[user][2]!r})")
for e in errors:
    print("  -", e)
sys.exit(1 if errors else 0)
PY
echo "    layout, fstab, auditd.conf, root lock and user ok"

# ---- 3. online checks --------------------------------------------------------------
step "booting the installed system with a one-shot check unit"
cat >"$WORK/syncopated-vmtest.service" <<'EOF'
[Unit]
Description=Syncopated VM install test
After=multi-user.target auditd.service
Wants=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'out=/var/lib/syncopated/vmtest; mkdir -p $out; \
  /usr/local/bin/syncopated-scan >$out/scan.log 2>&1; echo $? >$out/scan.rc; \
  auditctl -s >$out/auditctl.txt 2>&1; systemctl --failed --no-legend >$out/failed.txt; \
  systemctl is-system-running >$out/state.txt 2>&1; lsblk -o NAME,SIZE,MOUNTPOINTS >$out/lsblk.txt; \
  cp -a /var/lib/syncopated/scans $out/ 2>/dev/null; systemctl poweroff'

[Install]
WantedBy=multi-user.target
EOF
virt-customize -q -a "$DISK" \
  --upload "$WORK/syncopated-vmtest.service:/etc/systemd/system/syncopated-vmtest.service" \
  --run-command 'systemctl enable syncopated-vmtest.service' \
  --selinux-relabel || fail "virt-customize could not add the check unit"

if ! timeout "$BOOT_TIMEOUT" bash -c "$(declare -f qemu); MEM=$MEM CPUS=$CPUS WORK=$WORK DISK=$DISK ovmf_code=$ovmf_code qemu \
  -serial file:'$WORK/boot-serial.log'"; then
  fail "the installed system did not finish the checks within ${BOOT_TIMEOUT}s; see $WORK/boot-serial.log"
fi
rm -rf "$WORK/results"
mkdir -p "$WORK/results"
virt-copy-out -a "$DISK" /var/lib/syncopated/vmtest "$WORK/results" || fail "no results on the disk"
R=$WORK/results/vmtest

[ "$(cat "$R/scan.rc")" = 0 ] || fail "syncopated-scan failed: $(tail -5 "$R/scan.log")"
scan=$(find "$R/scans" -mindepth 1 -maxdepth 1 -type d | sort | tail -n1)
for f in stock-arf.xml stock-report.html tailored-arf.xml tailored-report.html summary.txt; do
  [ -s "$scan/$f" ] || fail "syncopated-scan did not write $f"
done
if [ "$HARDENING" != hipaa ]; then
  grep -Eq 'idref="xccdf_org.ssgproject.content_rule_audit_rules_dac_modification_chmod"[^>]*>.*' "$scan/tailored-arf.xml" ||
    fail "tailored ARF does not mention audit_rules_dac_modification_chmod"
fi
python3 - "$scan/tailored-arf.xml" <<'PY' || fail "the tailored scan evaluated a rule the tailoring unselects"
import re, sys
arf = open(sys.argv[1]).read()
for rule in ("auditd_data_retention_max_log_file_action", "auditd_data_retention_admin_space_left_action"):
    m = re.search(rf'idref="xccdf_org.ssgproject.content_rule_{rule}"[^>]*>.*?<result>(\w+)</result>', arf, re.S)
    if m and m.group(1) != "notselected":
        print(f"  - {rule}: {m.group(1)}")
        sys.exit(1)
PY
grep -q "enabled 1\|enabled 2" "$R/auditctl.txt" || fail "auditd is not enabled: $(cat "$R/auditctl.txt")"
state=$(cat "$R/state.txt")
case $state in running | degraded) ;; *) fail "system state is '$state'" ;; esac
echo "    syncopated-scan reports ok; auditd on; system $state; failed units: $(wc -l <"$R/failed.txt")"
cat "$scan/summary.txt"

echo "PASS: unattended install of $(basename "$ISO") (work dir $WORK)"
