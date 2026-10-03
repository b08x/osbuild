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
  disk vda 80
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
  grep -q "target disk vda has 30720 MiB; at least 40960 MiB (40 GiB) is required" "$SYNC_PRE_TTY"
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

@test "F11/F12: 60 GiB disk gets the / floor, a 4:1 /usr:/var split and no /home" {
  disk nvme0n1 60 nvme
  disk vdb 30
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 57344; reserve 5734; / = max(5734, 16384); rest 35226 -> 80/20
  diff -u - "$SYNC_PRE_OUT" <<EOF
ignoredisk --only-use=nvme0n1
zerombr
clearpart --all --initlabel --disklabel=gpt --drives=nvme0n1
bootloader --boot-drive=nvme0n1
reqpart
part /boot --size=2048 --fstype=xfs --ondisk=nvme0n1
part pv.00 --size=1 --grow --ondisk=nvme0n1
volgroup vg00 pv.00
logvol / --vgname=vg00 --name=root --size=16384 --fstype=xfs
logvol /usr --vgname=vg00 --name=usr --size=28180 --fstype=xfs
logvol /var --vgname=vg00 --name=var --size=7046 --fstype=xfs
EOF
  [[ "$output" == *"unassigned 5734 MiB"* ]]
}

@test "F12: 477 GiB disk caps /usr, /var takes the remainder and /home stays on /" {
  disk nvme0n1 477 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 484352; / 48435; reserve 48435; rest 387482; /usr cap 262144
  [ "$(lv /)" = 48435 ]
  [ "$(lv /usr)" = 262144 ]
  [ "$(lv /var)" = 125338 ]
  [ -z "$(lv /home)" ]
  [[ "$output" == *"unassigned 48435 MiB"* ]]
}

@test "F12: 931 GiB disk caps /usr and /var and gives /home the rest except the reserve" {
  disk nvme0n1 931 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 949248; / 94924; reserve 94924; rest 759400 -> 262144 + 131072 + 366184
  [ "$(lv /)" = 94924 ]
  [ "$(lv /usr)" = 262144 ]
  [ "$(lv /var)" = 131072 ]
  [ "$(lv /home)" = 366184 ]
  ! grep "^logvol" "$SYNC_PRE_OUT" | grep -q -- --grow
  [[ "$output" == *"unassigned 94924 MiB"* ]]
}

@test "layout env written by the role overrides the built-in defaults" {
  disk nvme0n1 60 nvme
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/layout.env"
  printf '%s\n' RESERVE_PCT=0 USR_PCT=50 HOME_MIN_MIB=1024 >"$SYNC_PRE_LAYOUT"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  # usable 57344; / 16384; rest 40960 -> 20480 / 20480; nothing left for /home
  [ "$(lv /usr)" = 20480 ]
  [ "$(lv /var)" = 20480 ]
  [ -z "$(lv /home)" ]
  [[ "$output" == *"unassigned 0 MiB"* ]]
}

@test "a layout that leaves no room for /usr and /var aborts" {
  disk vda 40
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/layout.env"
  printf '%s\n' ROOT_MIN_MIB=36000 >"$SYNC_PRE_LAYOUT"
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "less than 1 GiB for /usr or /var" "$SYNC_PRE_TTY"
}

@test "built-in layout defaults in the .ks equal the role defaults" {
  local defaults="$BATS_TEST_DIRNAME/../../defaults/main.yml"
  def() { sed -n "s/^osbuild_kickstart_$1: *\([0-9]*\)\$/\1/p" "$defaults"; }
  ks() { sed -n "s/^$1=\([0-9]*\) .*/\1/p" "$KS"; }
  [ "$(ks MIN_MIB)" = $(($(def disk_min_gib) * 1024)) ]
  [ "$(ks ROOT_PCT)" = "$(def root_percent)" ]
  [ "$(ks ROOT_MIN_MIB)" = $(($(def root_min_gib) * 1024)) ]
  [ "$(ks RESERVE_PCT)" = "$(def reserve_percent)" ]
  [ "$(ks USR_PCT)" = "$(def usr_percent)" ]
  [ "$(ks USR_MAX_MIB)" = $(($(def usr_max_gib) * 1024)) ]
  [ "$(ks VAR_MAX_MIB)" = $(($(def var_max_gib) * 1024)) ]
  [ "$(ks HOME_MIN_MIB)" = $(($(def home_min_gib) * 1024)) ]
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
