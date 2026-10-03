# Syncopated installer kickstart.
#
# tasks/blueprint.yml embeds this file in every prepared blueprint as
# [customizations.installer.kickstart] contents, after rendered lang, keyboard
# and timezone lines. image-builder puts its own payload %include in front.
# Edit this file, not the blueprints. It must not contain three consecutive
# single quotes (TOML literal string delimiter) or Jinja delimiters.
#
# Anaconda still asks for two things: Root Password and User Creation.

graphical
firstboot --disable
reboot
network --bootproto=dhcp --device=link --activate --onboot=on

# Pick one target disk and write its layout to /tmp/partitions.ks.
# Excluded: the disk holding the install media, removable, read-only and USB
# disks. NVMe disks win over other disks; among equals the largest wins.
%pre --interpreter=/usr/bin/bash --erroronfail --log=/tmp/syncopated-pre.log
set -uo pipefail

OUT=${SYNC_PRE_OUT:-/tmp/partitions.ks}
TTY=${SYNC_PRE_TTY:-/dev/tty1}
CMDLINE=${SYNC_PRE_CMDLINE:-/proc/cmdline}
LAYOUT=${SYNC_PRE_LAYOUT:-/tmp/syncopated-layout.env}

# Layout parameters, in MiB and percent. These values equal the role
# defaults; the role writes its osbuild_kickstart_* variables to $LAYOUT in an
# earlier %pre, which overrides them.
MIN_MIB=40960       # smallest target disk accepted
BUFFER_MIB=4096     # held back for /boot, the EFI partition and LVM metadata
ROOT_PCT=10         # / share of the usable space
ROOT_MIN_MIB=16384  # / floor
RESERVE_PCT=10      # share of the usable space left unassigned in vg00
USR_PCT=80          # /usr share of the space after / and the reserve
USR_MAX_MIB=262144  # /usr cap
VAR_MAX_MIB=131072  # /var cap
HOME_MIN_MIB=102400 # /home is created only when at least this much is left
# shellcheck source=/dev/null
[ -r "$LAYOUT" ] && . "$LAYOUT"

die() {
  echo "ERROR: $*" >&2
  echo "Syncopated install aborted: $*" >"$TTY" 2>/dev/null || true
  exit 1
}

# Whole-disk name behind a block device: a partition maps to its parent.
disk_of() {
  local parent
  parent=$(lsblk -no PKNAME "$1" 2>/dev/null | head -n1)
  if [ -n "$parent" ]; then
    echo "$parent"
  else
    lsblk -dno NAME "$1" 2>/dev/null | head -n1
  fi
}

media=()
for mnt in /run/install/repo /run/install/isodir; do
  src=$(findmnt -no SOURCE "$mnt" 2>/dev/null) || continue
  [ -n "$src" ] && media+=("$(disk_of "$src")")
done
# Fallback: the inst.stage2=hd:LABEL=... boot argument names the media label.
label=$(grep -o 'LABEL=[^ :]*' "$CMDLINE" 2>/dev/null | head -n1 | cut -d= -f2-)
if [ -n "$label" ]; then
  src=$(blkid -L "$(printf '%b' "$label")" 2>/dev/null) && [ -n "$src" ] && media+=("$(disk_of "$src")")
fi
echo "install media disks: ${media[*]:-none}"

best=
best_size=0
best_nvme=0
while read -r name type rm ro size tran; do
  [ "$type" = disk ] || continue
  case $name in zram* | loop* | sr*) continue ;; esac
  if [ "$rm" != 0 ] || [ "$ro" != 0 ]; then
    echo "skip $name: removable or read-only"
    continue
  fi
  if [ "${tran:-}" = usb ]; then
    echo "skip $name: usb"
    continue
  fi
  for m in "${media[@]}"; do
    if [ "$m" = "$name" ]; then
      echo "skip $name: install media"
      continue 2
    fi
  done
  nvme=0
  case $name in nvme*) nvme=1 ;; esac
  echo "candidate $name: $size bytes, nvme=$nvme"
  if [ "$nvme" -gt "$best_nvme" ] || { [ "$nvme" -eq "$best_nvme" ] && [ "$size" -gt "$best_size" ]; }; then
    best=$name
    best_size=$size
    best_nvme=$nvme
  fi
done < <(lsblk -dbno NAME,TYPE,RM,RO,SIZE,TRAN)

[ -n "$best" ] || die "no installable disk found (install media, removable, read-only and USB disks are excluded)"

total=$((best_size / 1048576))
[ "$total" -ge "$MIN_MIB" ] || die "target disk $best has $total MiB; at least $MIN_MIB MiB ($((MIN_MIB / 1024)) GiB) is required"

# / gets ROOT_PCT of the usable space (at least ROOT_MIN_MIB) and RESERVE_PCT
# stays unassigned in vg00 for lvextend. /usr gets USR_PCT of what is left,
# up to its cap; /var gets the remainder, up to its cap. Space beyond the caps becomes
# /home when it is at least HOME_MIN_MIB; otherwise it also stays unassigned
# and /home is a directory on /.
avail=$((total - BUFFER_MIB))
reserve=$((avail * RESERVE_PCT / 100))
root=$((avail * ROOT_PCT / 100))
[ "$root" -ge "$ROOT_MIN_MIB" ] || root=$ROOT_MIN_MIB
rest=$((avail - reserve - root))
usr=$((rest * USR_PCT / 100))
[ "$usr" -le "$USR_MAX_MIB" ] || usr=$USR_MAX_MIB
var=$((rest - usr))
[ "$var" -le "$VAR_MAX_MIB" ] || var=$VAR_MAX_MIB
if [ "$usr" -lt 1024 ] || [ "$var" -lt 1024 ]; then
  die "layout leaves less than 1 GiB for /usr or /var on $best ($total MiB); lower the / or reserve share"
fi
home=$((rest - usr - var))
[ "$home" -ge "$HOME_MIN_MIB" ] || home=0

cat >"$OUT" <<EOF
ignoredisk --only-use=$best
zerombr
clearpart --all --initlabel --disklabel=gpt --drives=$best
bootloader --boot-drive=$best
reqpart
part /boot --size=2048 --fstype=xfs --ondisk=$best
part pv.00 --size=1 --grow --ondisk=$best
volgroup vg00 pv.00
logvol / --vgname=vg00 --name=root --size=$root --fstype=xfs
logvol /usr --vgname=vg00 --name=usr --size=$usr --fstype=xfs
logvol /var --vgname=vg00 --name=var --size=$var --fstype=xfs
EOF
if [ "$home" -gt 0 ]; then
  echo "logvol /home --vgname=vg00 --name=home --size=$home --fstype=xfs" >>"$OUT"
fi
echo "target disk $best: $total MiB; / $root MiB, /usr $usr MiB, /var $var MiB, /home $home MiB (0: on /), unassigned $((avail - root - usr - var - home)) MiB"
%end

%include /tmp/partitions.ks

# Create the system flatpak repository so /etc/flatpak/remotes.d (the Flathub
# remote) is applied at install time. flatpak imports remotes.d files only
# when root first opens /var/lib/flatpak/repo; until then a user running
# `flatpak remotes` sees no remotes. Runs inside the installed system.
%post --interpreter=/usr/bin/bash --log=/root/syncopated-post.log
if command -v flatpak >/dev/null 2>&1; then
  flatpak remotes --system --columns=name,url
fi
%end
