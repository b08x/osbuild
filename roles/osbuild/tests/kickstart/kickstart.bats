#!/usr/bin/env bats
# Tests for the %pre disk selection in roles/osbuild/files/kickstart/syncopated.ks.
# Fact numbers refer to goals/kickstart-blueprint-directives/facts.md.
#
# The %pre body is extracted from the kickstart and run with stubbed lsblk,
# findmnt and blkid (tests/kickstart/stubs/). SYNC_PRE_OUT, SYNC_PRE_TTY and
# SYNC_PRE_CMDLINE point its outputs and /proc/cmdline at per-test files.
# SYNC_PRE_LAYOUT points at a missing file unless a test writes one, so the
# built-in layout defaults (equal to the role defaults) apply.

GIB=1073741824

setup_file() {
  ROLE_DIR="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  export KS="$ROLE_DIR/files/kickstart/syncopated.ks"
  export PRE="$BATS_FILE_TMPDIR/pre.sh"
  awk '/^%pre/{f=1;next} /^%end/{f=0} f' "$KS" >"$PRE"
}

setup() {
  export PATH="$BATS_TEST_DIRNAME/stubs:$PATH"
  export LSBLK_DISKS="$BATS_TEST_TMPDIR/disks"
  export LSBLK_PARENTS="$BATS_TEST_TMPDIR/parents"
  export FINDMNT_MAP="$BATS_TEST_TMPDIR/mounts"
  export BLKID_MAP="$BATS_TEST_TMPDIR/labels"
  export SYNC_PRE_OUT="$BATS_TEST_TMPDIR/partitions.ks"
  export SYNC_PRE_TTY="$BATS_TEST_TMPDIR/tty1"
  export SYNC_PRE_CMDLINE="$BATS_TEST_TMPDIR/cmdline"
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/no-layout.env"
  : >"$LSBLK_DISKS"
  : >"$LSBLK_PARENTS"
  : >"$FINDMNT_MAP"
  : >"$BLKID_MAP"
  echo "BOOT_IMAGE=/images/pxeboot/vmlinuz quiet" >"$SYNC_PRE_CMDLINE"
}

# disk NAME SIZE_GIB [TRAN] [RM] [RO] [TYPE]
disk() {
  echo "$1 ${6:-disk} ${4:-0} ${5:-0} $(($2 * GIB)) ${3:-}" >>"$LSBLK_DISKS"
}

target() {
  sed -n 's/^ignoredisk --only-use=//p' "$SYNC_PRE_OUT"
}

@test "F9: NVMe wins over a larger SATA disk" {
  disk sda 2000 sata
  disk nvme0n1 500 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = nvme0n1 ]
}

@test "F9: the largest NVMe disk wins among NVMe disks" {
  disk nvme0n1 256 nvme
  disk nvme1n1 1000 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = nvme1n1 ]
}

@test "F9: USB disks are excluded even when not flagged removable" {
  disk sdb 1000 usb
  disk sda 100 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
  [[ "$output" == *"skip sdb: usb"* ]]
}

@test "F9: removable and read-only disks are excluded" {
  disk sdb 1000 sata 1
  disk sdc 1000 sata 0 1
  disk sda 100 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
}

@test "F9: zram, loop and optical devices are never candidates" {
  disk zram0 64
  disk loop0 100 "" 0 0 loop
  disk sr0 1 sata 1 1 rom
  disk vda 100
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = vda ]
}

@test "F9: the disk behind /run/install/repo is excluded" {
  disk sdb 1000 sata
  disk sda 100 sata
  echo "/run/install/repo /dev/sdb1" >"$FINDMNT_MAP"
  echo "/dev/sdb1 sdb" >"$LSBLK_PARENTS"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
  [[ "$output" == *"skip sdb: install media"* ]]
}

@test "F9: an unpartitioned media disk is excluded by its own name" {
  disk sdb 1000 sata
  disk sda 100 sata
  echo "/run/install/repo /dev/sdb" >"$FINDMNT_MAP"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
}

@test "F9: the inst.stage2 LABEL identifies the media disk when nothing is mounted" {
  disk sdc 2000 sata
  disk sda 100 sata
  echo "BOOT_IMAGE=/images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Rocky-10-2-x86_64 quiet" >"$SYNC_PRE_CMDLINE"
  echo "Rocky-10-2-x86_64 /dev/sdc1" >"$BLKID_MAP"
  echo "/dev/sdc1 sdc" >"$LSBLK_PARENTS"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
}

@test "F9: the larger of two SATA disks wins" {
  disk sda 250 sata
  disk sdb 1000 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sdb ]
}

@test "F10: a 30 GiB target aborts with a readable error" {
  disk vda 30
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "target disk vda has 30720 MiB; at least 102400 MiB (100 GiB) is required" "$SYNC_PRE_TTY"
}

@test "F10: no candidate disk aborts with a readable error" {
  disk sdb 64 usb
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "no installable disk found" "$SYNC_PRE_TTY"
}

lv() {
  sed -n "s|^logvol $1 --vgname=vg00 --name=[a-z]* --size=\([0-9]*\) --fstype=xfs\$|\1|p" "$SYNC_PRE_OUT"
}

@test "F11/F12: 100 GiB disk gets the minimums plus a weighted share and no /home" {
  disk nvme0n1 100 nvme
  disk vdb 30
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 98304; reserve 7864; pool 90440; minimums / 20480, /usr 30720, /var 30720 (+ /home 20480 does not fit);
  # 8520 left shared 1:3:3 -> 1217, 3651, 3651 (1 MiB rounding stays unassigned)
  diff -u - "$SYNC_PRE_OUT" <<EOF
ignoredisk --only-use=nvme0n1
zerombr
clearpart --all --initlabel --disklabel=gpt --drives=nvme0n1
bootloader --boot-drive=nvme0n1
reqpart
part /boot --size=2048 --fstype=xfs --ondisk=nvme0n1
part pv.00 --size=1 --grow --ondisk=nvme0n1
volgroup vg00 pv.00
logvol / --vgname=vg00 --name=root --size=21697 --fstype=xfs
logvol /usr --vgname=vg00 --name=usr --size=34371 --fstype=xfs
logvol /var --vgname=vg00 --name=var --size=34371 --fstype=xfs
EOF
  [[ "$output" == *"unassigned 7865 MiB"* ]]
}

@test "F12: 477 GiB disk caps /usr and /var at 110 GiB and /home gets the remainder" {
  disk nvme0n1 477 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 484352; reserve 38748; pool 445604; minimums 102400; 343204 left shared 1:3:3:5;
  # /usr and /var reach their 112640 cap, / and /home share the rest
  [ "$(lv /)" = 50373 ]
  [ "$(lv /usr)" = 112640 ]
  [ "$(lv /var)" = 112640 ]
  [ "$(lv /home)" = 169950 ]
  [[ "$output" == *"unassigned 38749 MiB"* ]]
}

@test "F12: 931 GiB disk caps / at 64 GiB and the reserve at 64 GiB" {
  disk nvme0n1 931 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(lv /)" = 65536 ]
  [ "$(lv /usr)" = 112640 ]
  [ "$(lv /var)" = 112640 ]
  [ "$(lv /home)" = 592896 ]
  ! grep "^logvol" "$SYNC_PRE_OUT" | grep -q -- --grow
  [[ "$output" == *"unassigned 65536 MiB"* ]]
}

@test "119 GiB disk still gets a /home volume and a /usr above its 30 GiB minimum" {
  disk sdc 119 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(lv /usr)" = 32205 ]
  [ "$(lv /var)" = 32205 ]
  [ "$(lv /home)" = 22955 ]
}

@test "233 GiB disk shares the space by weight" {
  disk sdc 233 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(lv /)" = 29924 ]
  [ "$(lv /usr)" = 59054 ]
  [ "$(lv /var)" = 59054 ]
  [ "$(lv /home)" = 67703 ]
}

@test "layout env written by the role overrides the built-in defaults" {
  disk nvme0n1 100 nvme
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/layout.env"
  printf '%s\n' RESERVE_PCT=0 ROOT_W=0 USR_W=1 VAR_W=1 >"$SYNC_PRE_LAYOUT"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 98304, no reserve; minimums 20480 + 30720 + 30720 (no /home); 16384 left -> 8192 each to /usr and /var
  [ "$(lv /)" = 20480 ]
  [ "$(lv /usr)" = 38912 ]
  [ "$(lv /var)" = 38912 ]
  [ -z "$(lv /home)" ]
  [[ "$output" == *"unassigned 0 MiB"* ]]
}

@test "auto: the NVIDIA playbooks' /usr minimum of 80 GiB (role vars) is applied" {
  disk nvme0n1 150 nvme
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/layout.env"
  printf '%s\n' MIN_MIB=153600 USR_MIN_MIB=81920 >"$SYNC_PRE_LAYOUT"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 149504; reserve 11960; pool 137544; minimums 20480 + 81920 + 30720; 4424 left shared 1:3:3
  [ "$(lv /)" = 21112 ]
  [ "$(lv /usr)" = 83816 ]
  [ "$(lv /var)" = 32616 ]
  [ -z "$(lv /home)" ]
}

@test "auto: a 120 GiB disk is too small for an 80 GiB /usr minimum" {
  disk nvme0n1 120 nvme
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/layout.env"
  printf '%s\n' USR_MIN_MIB=81920 >"$SYNC_PRE_LAYOUT"
  run bash "$PRE"
  [ "$status" -eq 1 ]
  grep -q "do not fit" "$SYNC_PRE_TTY"
}

@test "minimums that do not fit abort" {
  disk vda 150
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/layout.env"
  printf '%s\n' ROOT_MIN_MIB=90000 >"$SYNC_PRE_LAYOUT"
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "do not fit" "$SYNC_PRE_TTY"
}

@test "built-in layout defaults in the .ks equal the role defaults" {
  local defaults="$BATS_TEST_DIRNAME/../../defaults/main.yml"
  def() { sed -n "s/^osbuild_kickstart_$1: *\([0-9]*\)\$/\1/p" "$defaults"; }
  ks() { sed -n "s/^$1=\([0-9]*\)\( .*\)\{0,1\}\$/\1/p" "$KS"; }
  [ "$(ks MIN_MIB)" = $(($(def disk_min_gib) * 1024)) ]
  [ "$(ks RESERVE_PCT)" = "$(def reserve_percent)" ]
  [ "$(ks RESERVE_MAX_MIB)" = $(($(def reserve_max_gib) * 1024)) ]
  for v in ROOT USR VAR; do
    lower=$(echo "$v" | tr A-Z a-z)
    [ "$(ks ${v}_MIN_MIB)" = $(($(def ${lower}_min_gib) * 1024)) ]
    [ "$(ks ${v}_MAX_MIB)" = $(($(def ${lower}_max_gib) * 1024)) ]
    [ "$(ks ${v}_W)" = "$(def ${lower}_weight)" ]
  done
  [ "$(ks HOME_MIN_MIB)" = $(($(def home_min_gib) * 1024)) ]
  [ "$(ks HOME_W)" = "$(def home_weight)" ]
}

@test "F6: the kickstart with a generated layout passes ksvalidator" {
  local ksv
  ksv=$(command -v ksvalidator || echo "$BATS_TEST_DIRNAME/../../../../.venv/bin/ksvalidator")
  [ -x "$ksv" ] || skip "ksvalidator not installed"
  disk nvme0n1 500 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  sed "s|^%include /tmp/partitions.ks|%include $SYNC_PRE_OUT|" "$KS" >"$BATS_TEST_TMPDIR/full.ks"
  for v in RHEL9 RHEL10 F43; do
    run "$ksv" -i -v "$v" "$BATS_TEST_TMPDIR/full.ks"
    echo "$v: $output"
    [ "$status" -eq 0 ]
  done
}

# --- compliant layout (LAYOUT_MODE=compliant) -------------------------------

clv() {
  sed -n "s|^logvol $1 --vgname=vg00 --name=[a-z_]* --size=\([0-9]*\) .*|\1|p" "$SYNC_PRE_OUT"
}

compliant() {
  printf 'LAYOUT_MODE=compliant\n%s\n' "$*" >"$SYNC_PRE_LAYOUT"
  export SYNC_PRE_POST_OUT="$BATS_TEST_TMPDIR/partitions-post.ks"
}

@test "compliant: 477 GiB disk gets every separate mount with hardening options" {
  disk nvme0n1 477 nvme
  compliant ""
  run bash "$PRE"
  [ "$status" -eq 0 ]
  for mp in /usr /var /var/tmp /var/log /var/log/audit /home; do
    grep -q "^logvol $mp " "$SYNC_PRE_OUT"
  done
  ! grep -q "^logvol /tmp " "$SYNC_PRE_OUT"
  grep -q '^logvol /var/tmp .*--fsoptions="nodev,nosuid,noexec[,"]' "$SYNC_PRE_OUT"
  grep -q '^logvol /home .*--fsoptions="nodev,nosuid[,"]' "$SYNC_PRE_OUT"
  grep -q '^part /boot .*--fsoptions="nodev,nosuid"' "$SYNC_PRE_OUT"
  ! grep -q -- '--encrypted' "$SYNC_PRE_OUT"
  # usable 484352; reserve 38748; pool 445604; fixed 110592 + /var min 40960 + /home min 10240;
  # 283812 left shared 2:5 -> /var +81089, /home +202723
  [ "$(clv /var)" = 122049 ]
  [ "$(clv /home)" = 212962 ]
  [[ "$output" == *"unassigned 38749 MiB"* ]]
}

@test "compliant: tmpfs /tmp is an fstab line in a %post include" {
  disk nvme0n1 477 nvme
  compliant ""
  run bash "$PRE"
  [ "$status" -eq 0 ]
  grep -q '^%post' "$SYNC_PRE_POST_OUT"
  grep -q 'tmpfs /tmp tmpfs defaults,nodev,nosuid,noexec' "$SYNC_PRE_POST_OUT"
  [ "$(tail -n1 "$SYNC_PRE_POST_OUT")" = "%end" ]
}

@test "compliant: TMP_MODE=lv adds a /tmp volume and an empty %post include" {
  disk nvme0n1 477 nvme
  compliant "TMP_MODE=lv"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  grep -q '^logvol /tmp .*noexec' "$SYNC_PRE_OUT"
  [ ! -s "$SYNC_PRE_POST_OUT" ]
}

@test "compliant: ENCRYPT=1 encrypts the physical volume" {
  disk nvme0n1 477 nvme
  compliant "ENCRYPT=1"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  grep -q '^part pv.00 .*--encrypted' "$SYNC_PRE_OUT"
}

@test "compliant: 932 GiB disk clamps /var and gives the rest to /home" {
  disk nvme0n1 932 nvme
  compliant ""
  run bash "$PRE"
  [ "$status" -eq 0 ]
  var=$(sed -n 's/^logvol \/var --.*--size=\([0-9]*\).*/\1/p' "$SYNC_PRE_OUT")
  home=$(sed -n 's/^logvol \/home --.*--size=\([0-9]*\).*/\1/p' "$SYNC_PRE_OUT")
  [ "$var" = 204800 ]
  [ "$home" = 569344 ]
  [[ "$output" == *"unassigned 65536 MiB"* ]]
}

@test "compliant: a 100 GiB disk aborts below the compliant minimum" {
  disk nvme0n1 100 nvme
  compliant ""
  run bash "$PRE"
  [ "$status" -ne 0 ]
  [[ "$output" == *"at least"* ]]
}

@test "compliant: a 180 GiB disk (the minimum) fits the default layout with /home >= 10 GiB" {
  disk nvme0n1 180 nvme
  compliant ""
  run bash "$PRE"
  [ "$status" -eq 0 ]
  home=$(sed -n 's/^logvol \/home --.*--size=\([0-9]*\).*/\1/p' "$SYNC_PRE_OUT")
  [ "$home" -ge 10240 ]
}

@test "compliant: the NVIDIA playbook's 80 GiB /usr (role var) needs 215 GiB" {
  disk nvme0n1 215 nvme
  compliant "MIN_MIB=220160
C_USR_MIB=81920"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(clv /usr)" = 81920 ]
}

@test "compliant: a 179 GiB disk aborts" {
  disk nvme0n1 179 nvme
  compliant ""
  run bash "$PRE"
  [ "$status" -ne 0 ]
}

@test "built-in compliant defaults in the .ks equal the role defaults" {
  local defaults="$BATS_TEST_DIRNAME/../../defaults/main.yml"
  def() { sed -n "s/^osbuild_kickstart_compliant_$1: *\([0-9]*\)\$/\1/p" "$defaults"; }
  ks() { sed -n "s/^$1=\([0-9]*\)\( .*\)\{0,1\}\$/\1/p" "$KS"; }
  [ "$(ks C_ROOT_MIB)" = $(($(def root_gib) * 1024)) ]
  [ "$(ks C_USR_MIB)" = $(($(def usr_gib) * 1024)) ]
  [ "$(ks C_VAR_MIN_MIB)" = $(($(def var_min_gib) * 1024)) ]
  [ "$(ks C_VAR_MAX_MIB)" = $(($(def var_max_gib) * 1024)) ]
  [ "$(ks C_VAR_W)" = "$(def var_weight)" ]
  [ "$(ks C_HOME_MIN_MIB)" = $(($(def home_min_gib) * 1024)) ]
  [ "$(ks C_HOME_W)" = "$(def home_weight)" ]
  [ "$(ks C_TMP_MIB)" = $(($(def tmp_gib) * 1024)) ]
  [ "$(ks C_VARTMP_MIB)" = $(($(def var_tmp_gib) * 1024)) ]
  [ "$(ks C_VARLOG_MIB)" = $(($(def var_log_gib) * 1024)) ]
  [ "$(ks C_AUDIT_MIB)" = $(($(def audit_gib) * 1024)) ]
}
