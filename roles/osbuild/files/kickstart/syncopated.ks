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
OUT_POST=${SYNC_PRE_POST_OUT:-/tmp/partitions-post.ks}

# Layout parameters, in MiB, percent and weights. These values equal the role
# defaults; the role writes its osbuild_kickstart_* variables to $LAYOUT in an
# earlier %pre, which overrides them.
#
# Both layouts size volumes the way Anaconda's default_partitioning and
# systemd-repart do: every volume starts at its minimum, and the space that is
# left (usable - reserve - the minimums) is shared in proportion to the weights
# until a volume reaches its maximum. Space no volume can take stays unassigned.
MIN_MIB=102400      # smallest target disk accepted
BUFFER_MIB=4096     # held back for /boot, the EFI partition and LVM metadata
RESERVE_PCT=8       # share of the usable space left unassigned in vg00 ...
RESERVE_MAX_MIB=65536 # ... at most this much
ROOT_MIN_MIB=20480  # /
ROOT_MAX_MIB=65536
ROOT_W=1
USR_MIN_MIB=30720   # /usr
USR_MAX_MIB=112640
USR_W=3
VAR_MIN_MIB=30720   # /var
VAR_MAX_MIB=112640
VAR_W=3
HOME_MIN_MIB=20480  # /home is dropped (a directory on /) when the minimums do not fit with it
HOME_W=5            # /home has no maximum

# LAYOUT_MODE=compliant (role: osbuild_kickstart_partitioning: compliant) swaps
# the layout below for one with the separate mounts that the CIS, PCI-DSS and
# HIPAA profiles scan for. Sizes in MiB; the role overrides them through $LAYOUT.
# The fixed volumes have equal minimum and maximum; /var and /home share the rest.
LAYOUT_MODE=auto
C_ROOT_MIB=35840    # /
C_USR_MIB=46080     # /usr
C_TMP_MIB=8192      # /tmp (volume, or tmpfs size limit)
C_VARTMP_MIB=8192   # /var/tmp
C_VARLOG_MIB=10240  # /var/log
C_AUDIT_MIB=10240   # /var/log/audit
C_VAR_MIN_MIB=40960 # /var
C_VAR_MAX_MIB=204800
C_VAR_W=2
C_HOME_MIN_MIB=10240 # /home must get at least this much
C_HOME_W=5
TMP_MODE=tmpfs      # tmpfs | lv
ENCRYPT=0           # 1: LUKS on the physical volume (Anaconda asks for a passphrase)
# shellcheck source=/dev/null
[ -r "$LAYOUT" ] && . "$LAYOUT"
if [ "$LAYOUT_MODE" = compliant ] && [ "$MIN_MIB" -eq 102400 ]; then
  MIN_MIB=184320    # compliant fixed volumes need a bigger disk (180 GiB)
fi
: >"$OUT_POST"

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

avail=$((total - BUFFER_MIB))
reserve=$((avail * RESERVE_PCT / 100))
[ "$reserve" -le "$RESERVE_MAX_MIB" ] || reserve=$RESERVE_MAX_MIB
pool=$((avail - reserve))

declare -A vmin vmax vwt size
vols=()
left=0
NO_MAX=$((1 << 50))

# add_vol NAME MIN MAX WEIGHT
add_vol() {
  vols+=("$1")
  vmin[$1]=$2
  vmax[$1]=$3
  vwt[$1]=$4
}

# allocate: size[] = minimums, then the remaining pool shared by weight in
# rounds, each volume capped at its maximum; what no volume can take stays in
# $left (unassigned).
allocate() {
  local v tw add cap round used
  left=$pool
  for v in "${vols[@]}"; do
    size[$v]=${vmin[$v]}
    left=$((left - vmin[$v]))
  done
  [ "$left" -ge 0 ] || return 1
  while [ "$left" -gt 0 ]; do
    tw=0
    for v in "${vols[@]}"; do
      [ "${size[$v]}" -lt "${vmax[$v]}" ] && tw=$((tw + vwt[$v]))
    done
    [ "$tw" -gt 0 ] || break
    round=$left
    used=0
    for v in "${vols[@]}"; do
      [ "${size[$v]}" -lt "${vmax[$v]}" ] || continue
      add=$((round * vwt[$v] / tw))
      cap=$((vmax[$v] - size[$v]))
      [ "$add" -le "$cap" ] || add=$cap
      size[$v]=$((size[$v] + add))
      used=$((used + add))
    done
    [ "$used" -gt 0 ] || break
    left=$((left - used))
  done
}

if [ "$LAYOUT_MODE" = compliant ]; then
  # Fixed volumes (minimum = maximum), then /var and /home share the rest after
  # the unassigned reserve. Mount options are set here because Anaconda
  # writes /etc/fstab at install time, after the build-time remediation.
  tmplv=0
  [ "$TMP_MODE" = lv ] && tmplv=$C_TMP_MIB
  add_vol root "$C_ROOT_MIB" "$C_ROOT_MIB" 0
  add_vol usr "$C_USR_MIB" "$C_USR_MIB" 0
  add_vol vartmp "$C_VARTMP_MIB" "$C_VARTMP_MIB" 0
  add_vol varlog "$C_VARLOG_MIB" "$C_VARLOG_MIB" 0
  add_vol audit "$C_AUDIT_MIB" "$C_AUDIT_MIB" 0
  [ "$tmplv" -eq 0 ] || add_vol tmp "$tmplv" "$tmplv" 0
  add_vol var "$C_VAR_MIN_MIB" "$C_VAR_MAX_MIB" "$C_VAR_W"
  add_vol home "$C_HOME_MIN_MIB" "$NO_MAX" "$C_HOME_W"
  allocate || die "compliant layout needs more than the $((pool)) MiB available on $best ($total MiB) for its fixed volumes plus at least $C_VAR_MIN_MIB MiB /var and $C_HOME_MIN_MIB MiB /home"
  var=${size[var]}
  home=${size[home]}
  enc=
  [ "$ENCRYPT" = 1 ] && enc=" --encrypted"
  cat >"$OUT" <<EOF
ignoredisk --only-use=$best
zerombr
clearpart --all --initlabel --disklabel=gpt --drives=$best
bootloader --boot-drive=$best
reqpart
part /boot --size=2048 --fstype=xfs --fsoptions="nodev,nosuid" --ondisk=$best
part pv.00 --size=1 --grow --ondisk=$best$enc
volgroup vg00 pv.00
logvol / --vgname=vg00 --name=root --size=$C_ROOT_MIB --fstype=xfs --fsoptions="noatime"
logvol /usr --vgname=vg00 --name=usr --size=$C_USR_MIB --fstype=xfs --fsoptions="nodev,noatime"
logvol /var --vgname=vg00 --name=var --size=$var --fstype=xfs --fsoptions="nodev,nosuid,noatime"
logvol /var/tmp --vgname=vg00 --name=var_tmp --size=$C_VARTMP_MIB --fstype=xfs --fsoptions="nodev,nosuid,noexec,noatime"
logvol /var/log --vgname=vg00 --name=var_log --size=$C_VARLOG_MIB --fstype=xfs --fsoptions="nodev,nosuid,noexec,noatime"
logvol /var/log/audit --vgname=vg00 --name=var_log_audit --size=$C_AUDIT_MIB --fstype=xfs --fsoptions="nodev,nosuid,noexec,noatime"
logvol /home --vgname=vg00 --name=home --size=$home --fstype=xfs --fsoptions="nodev,nosuid,noatime"
EOF
  if [ "$TMP_MODE" = lv ]; then
    echo "logvol /tmp --vgname=vg00 --name=tmp --size=$C_TMP_MIB --fstype=xfs --fsoptions=\"nodev,nosuid,noexec\"" >>"$OUT"
  else
    # printf keeps a line starting with %end out of this script: Anaconda would
    # end the %pre section there.
    printf '%s\n' \
      '%post --interpreter=/usr/bin/bash' \
      "echo 'tmpfs /tmp tmpfs defaults,nodev,nosuid,noexec,mode=1777,size=${C_TMP_MIB}M 0 0' >>/etc/fstab" \
      '%end' >"$OUT_POST"
  fi
  echo "target disk $best: $total MiB, compliant layout (/tmp=$TMP_MODE, encrypt=$ENCRYPT); / $C_ROOT_MIB, /usr $C_USR_MIB, /var $var, /home $home MiB, unassigned $((reserve + left)) MiB"
  exit 0
fi

# Every volume starts at its minimum; the space left after the reserve is shared
# by weight up to each maximum (see the parameters above). /home is optional:
# when the minimums do not fit with it, it is dropped and /home is a directory
# on /; the other volumes then share its space.
add_vol root "$ROOT_MIN_MIB" "$ROOT_MAX_MIB" "$ROOT_W"
add_vol usr "$USR_MIN_MIB" "$USR_MAX_MIB" "$USR_W"
add_vol var "$VAR_MIN_MIB" "$VAR_MAX_MIB" "$VAR_W"
add_vol home "$HOME_MIN_MIB" "$NO_MAX" "$HOME_W"
if ! allocate; then
  unset 'vols[3]'
  vols=("${vols[@]}")
  allocate || die "the minimum / ($ROOT_MIN_MIB), /usr ($USR_MIN_MIB) and /var ($VAR_MIN_MIB) MiB do not fit in the $pool MiB available on $best ($total MiB)"
  size[home]=0
fi
root=${size[root]}
usr=${size[usr]}
var=${size[var]}
home=${size[home]}

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
echo "target disk $best: $total MiB; / $root MiB, /usr $usr MiB, /var $var MiB, /home $home MiB (0: on /), unassigned $((reserve + left)) MiB"
%end

%include /tmp/partitions.ks
%include /tmp/partitions-post.ks

# Create the system flatpak repository so /etc/flatpak/remotes.d (the Flathub
# remote) is applied at install time. flatpak imports remotes.d files only
# when root first opens /var/lib/flatpak/repo; until then a user running
# `flatpak remotes` sees no remotes. Runs inside the installed system.
%post --interpreter=/usr/bin/bash --log=/root/syncopated-post.log
if command -v flatpak >/dev/null 2>&1; then
  flatpak remotes --system --columns=name,url
fi
# The OpenSCAP remediation (CIS) can mask cockpit at build time. Unmask it here,
# after the payload is installed, so the web console stays available.
# Harmless when cockpit is not installed.
systemctl unmask cockpit.socket cockpit.service || true
systemctl enable cockpit.socket || true
%end
