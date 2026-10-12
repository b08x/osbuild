#!/usr/bin/env bats
# Tests for the %pre in roles/osbuild/files/kickstart/syncopated.ks: disk
# selection, the serial and capacity guards, the countdown, and filling the
# generation-time layout in for the chosen disk.
#
# The %pre body is extracted from the kickstart and run with stubbed lsblk,
# findmnt, blkid and chvt (tests/kickstart/stubs/). SYNC_PRE_* variables point
# its inputs and outputs at per-test files. The layout files stand in for
# what templates/kickstart.toml.j2 renders; tests/test_intent.py checks the
# real rendered files (and runs ksvalidator on them).
# Volume sizes are no longer computed here: tests/test_disk_sizing.py.

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
  export LSBLK_INFO="$BATS_TEST_TMPDIR/info"
  export FINDMNT_MAP="$BATS_TEST_TMPDIR/mounts"
  export BLKID_MAP="$BATS_TEST_TMPDIR/labels"
  export CHVT_LOG="$BATS_TEST_TMPDIR/chvt"
  export SYNC_PRE_OUT="$BATS_TEST_TMPDIR/partitions.ks"
  export SYNC_PRE_TTY="$BATS_TEST_TMPDIR/tty1"
  export SYNC_PRE_COUNTDOWN_TTY="$BATS_TEST_TMPDIR/tty8"
  export SYNC_PRE_COUNTDOWN_IN="$BATS_TEST_TMPDIR/keys"
  export SYNC_PRE_SLEEP=:
  export SYNC_PRE_CMDLINE="$BATS_TEST_TMPDIR/cmdline"
  export SYNC_PRE_LAYOUT="$BATS_TEST_TMPDIR/layout.env"
  export SYNC_PRE_LAYOUT_KS="$BATS_TEST_TMPDIR/layout.ks"
  : >"$LSBLK_DISKS"
  : >"$LSBLK_PARENTS"
  : >"$LSBLK_INFO"
  : >"$FINDMNT_MAP"
  : >"$BLKID_MAP"
  : >"$SYNC_PRE_COUNTDOWN_IN"
  echo "BOOT_IMAGE=/images/pxeboot/vmlinuz quiet" >"$SYNC_PRE_CMDLINE"
  layout 100
}

# disk NAME SIZE_GIB [TRAN] [RM] [RO] [TYPE]
disk() {
  echo "$1 ${6:-disk} ${4:-0} ${5:-0} $(($2 * GIB)) ${3:-}" >>"$LSBLK_DISKS"
}

# info NAME SERIAL MODEL...
info() {
  echo "$*" >>"$LSBLK_INFO"
}

# layout DECLARED_GIB [SERIAL] [HOME_MIB]: the files the first %pre writes.
# HOME_MIB 0 leaves the /home volume out.
layout() {
  printf 'DECLARED_MIB=%s\nDISK_SERIAL=%s\nCOUNTDOWN=30\n' "$(($1 * 1024))" "${2:-}" >"$SYNC_PRE_LAYOUT"
  cat >"$SYNC_PRE_LAYOUT_KS" <<EOF
ignoredisk --only-use=@DISK@
zerombr
clearpart --all --initlabel --disklabel=gpt --drives=@DISK@
bootloader --boot-drive=@DISK@
reqpart
part /boot --size=2048 --fstype=xfs --ondisk=@DISK@
part pv.00 --size=1 --grow --ondisk=@DISK@
volgroup vg00 pv.00
logvol / --vgname=vg00 --name=root --size=21697 --fstype=xfs
logvol /usr --vgname=vg00 --name=usr --size=34371 --fstype=xfs
logvol /var --vgname=vg00 --name=var --size=34371 --fstype=xfs
EOF
  if [ "${3:-1000}" != 0 ]; then
    echo "logvol /home --vgname=vg00 --name=home --size=${3:-1000} --fstype=xfs --fsoptions=\"nodev,nosuid,noatime\"" >>"$SYNC_PRE_LAYOUT_KS"
  fi
}

target() {
  sed -n 's/^ignoredisk --only-use=//p' "$SYNC_PRE_OUT"
}

home() {
  sed -n 's/^logvol \/home .*--size=\([0-9]*\).*/\1/p' "$SYNC_PRE_OUT"
}

# ---- disk selection (unchanged) ----------------------------------------------

@test "NVMe wins over a larger SATA disk" {
  disk sda 2000 sata
  disk nvme0n1 500 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = nvme0n1 ]
}

@test "the largest NVMe disk wins among NVMe disks" {
  disk nvme0n1 256 nvme
  disk nvme1n1 1000 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = nvme1n1 ]
}

@test "the larger of two SATA disks wins" {
  disk sda 250 sata
  disk sdb 1000 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sdb ]
}

@test "USB disks are excluded even when not flagged removable" {
  disk sdb 1000 usb
  disk sda 100 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
  [[ "$output" == *"skip sdb: usb"* ]]
}

@test "removable and read-only disks are excluded" {
  disk sdb 1000 sata 1
  disk sdc 1000 sata 0 1
  disk sda 100 sata
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
}

@test "zram, loop and optical devices are never candidates" {
  disk zram0 64
  disk loop0 100 "" 0 0 loop
  disk sr0 1 sata 1 1 rom
  disk vda 100
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = vda ]
}

@test "the disk behind /run/install/repo is excluded" {
  disk sdb 1000 sata
  disk sda 100 sata
  echo "/run/install/repo /dev/sdb1" >"$FINDMNT_MAP"
  echo "/dev/sdb1 sdb" >"$LSBLK_PARENTS"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
  [[ "$output" == *"skip sdb: install media"* ]]
}

@test "an unpartitioned media disk is excluded by its own name" {
  disk sdb 1000 sata
  disk sda 100 sata
  echo "/run/install/repo /dev/sdb" >"$FINDMNT_MAP"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
}

@test "the inst.stage2 LABEL identifies the media disk when nothing is mounted" {
  disk sdc 2000 sata
  disk sda 100 sata
  echo "BOOT_IMAGE=/images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Rocky-10-2-x86_64 quiet" >"$SYNC_PRE_CMDLINE"
  echo "Rocky-10-2-x86_64 /dev/sdc1" >"$BLKID_MAP"
  echo "/dev/sdc1 sdc" >"$LSBLK_PARENTS"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = sda ]
}

@test "no candidate disk aborts with a readable error" {
  disk sdb 64 usb
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "no installable disk found" "$SYNC_PRE_TTY"
}

# ---- layout from generation time ---------------------------------------------

@test "a disk of exactly the declared size gets the rendered layout verbatim" {
  disk nvme0n1 100 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  diff -u <(sed 's/@DISK@/nvme0n1/g' "$SYNC_PRE_LAYOUT_KS") "$SYNC_PRE_OUT"
}

@test "%pre computes no volume sizes: every logvol size comes from the layout file" {
  ! grep -Eq 'allocate|_MIN_MIB|_W=|RESERVE' "$PRE"
}

@test "a larger disk gives the surplus to /home and nothing else changes" {
  layout 100 "" 1000
  disk nvme0n1 150 nvme
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(home)" = $((1000 + 50 * 1024)) ]
  diff -u <(sed 's/@DISK@/nvme0n1/g' "$SYNC_PRE_LAYOUT_KS" | grep -v '^logvol /home') \
    <(grep -v '^logvol /home' "$SYNC_PRE_OUT")
  grep -q -- '--fsoptions="nodev,nosuid,noatime"' "$SYNC_PRE_OUT"
}

@test "without a /home volume the surplus stays unassigned" {
  layout 100 "" 0
  disk vda 300
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ -z "$(home)" ]
  diff -u <(sed 's/@DISK@/vda/g' "$SYNC_PRE_LAYOUT_KS") "$SYNC_PRE_OUT"
}

@test "a disk smaller than declared aborts naming both sizes, before writing a layout" {
  layout 476
  disk nvme0n1 465 nvme
  info nvme0n1 S5GXNF0 Samsung SSD 980 PRO 500GB
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "target disk nvme0n1 (Samsung SSD 980 PRO 500GB) has 465 GiB (476160 MiB), but the profile declares disk.size_gib 476 GiB (487424 MiB)" "$SYNC_PRE_TTY"
  # aborted before the countdown
  [ ! -s "$CHVT_LOG" ]
}

@test "missing layout files abort: only role-generated kickstarts install" {
  rm "$SYNC_PRE_LAYOUT_KS"
  disk vda 100
  run bash "$PRE"
  [ "$status" -eq 1 ]
  grep -q "syncopated-layout.ks\|layout.ks is missing" "$SYNC_PRE_TTY"
}

# ---- serial pin ----------------------------------------------------------------

@test "a pinned serial that matches proceeds" {
  layout 100 S5GXNF0R123
  disk nvme0n1 100 nvme
  info nvme0n1 S5GXNF0R123 Samsung SSD
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(target)" = nvme0n1 ]
}

@test "a pinned serial that differs aborts before any disk is touched" {
  layout 100 S5GXNF0R123
  disk nvme0n1 100 nvme
  info nvme0n1 OTHER999 Samsung SSD
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "has serial 'OTHER999', but the profile pins disk.serial 'S5GXNF0R123'" "$SYNC_PRE_TTY"
  [ ! -s "$CHVT_LOG" ]
}

@test "a pinned serial with a disk that reports none aborts" {
  layout 100 S5GXNF0R123
  disk vda 100
  run bash "$PRE"
  [ "$status" -eq 1 ]
  grep -q "has serial 'none'" "$SYNC_PRE_TTY"
}

# ---- countdown -------------------------------------------------------------------

@test "the countdown names the disk model, serial and size, then proceeds" {
  disk nvme0n1 100 nvme
  info nvme0n1 S5GXNF0 Samsung SSD 980 PRO 500GB
  run bash "$PRE"
  [ "$status" -eq 0 ]
  grep -q "Target disk:  /dev/nvme0n1" "$SYNC_PRE_COUNTDOWN_TTY"
  grep -q "Model:        Samsung SSD 980 PRO 500GB" "$SYNC_PRE_COUNTDOWN_TTY"
  grep -q "Serial:       S5GXNF0" "$SYNC_PRE_COUNTDOWN_TTY"
  grep -q "Size:         100 GiB" "$SYNC_PRE_COUNTDOWN_TTY"
  grep -q "Press any key within 30 seconds to abort" "$SYNC_PRE_COUNTDOWN_TTY"
  grep -q "Installing in   1 s" "$SYNC_PRE_COUNTDOWN_TTY"
  # switched to the countdown console and back to tty1
  [ "$(cat "$CHVT_LOG")" = "$(printf '8\n1')" ]
}

@test "a key during the countdown aborts without writing a layout" {
  disk vda 100
  echo x >"$SYNC_PRE_COUNTDOWN_IN"
  run bash "$PRE"
  [ "$status" -eq 1 ]
  [ ! -e "$SYNC_PRE_OUT" ]
  grep -q "a key was pressed during the countdown; no disk was changed" "$SYNC_PRE_TTY"
}

@test "the countdown takes one second per step when the console gives no input" {
  disk vda 100
  printf 'DECLARED_MIB=102400\nDISK_SERIAL=\nCOUNTDOWN=3\n' >"$SYNC_PRE_LAYOUT"
  export SYNC_PRE_SLEEP="$BATS_TEST_TMPDIR/sleep"
  printf '#!/bin/sh\necho "$1" >>"%s"\n' "$BATS_TEST_TMPDIR/slept" >"$SYNC_PRE_SLEEP"
  chmod +x "$SYNC_PRE_SLEEP"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  [ "$(wc -l <"$BATS_TEST_TMPDIR/slept")" -eq 3 ]
}

@test "the countdown length comes from the layout file" {
  disk vda 100
  printf 'DECLARED_MIB=102400\nDISK_SERIAL=\nCOUNTDOWN=5\n' >"$SYNC_PRE_LAYOUT"
  run bash "$PRE"
  [ "$status" -eq 0 ]
  grep -q "Press any key within 5 seconds" "$SYNC_PRE_COUNTDOWN_TTY"
}

@test "the kickstart includes the generated layout and nothing else for storage" {
  grep -q '^%include /tmp/partitions.ks$' "$KS"
  ! grep -q 'partitions-post.ks' "$KS"
  ! grep -Eq '^(autopart|part|logvol|clearpart|rootpw|user) ' "$KS"
}
