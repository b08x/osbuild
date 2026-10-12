#!/usr/bin/bash
# syncopated-audit-warn: warn while the audit log volume is nearly full.
#
# Installed as /usr/local/sbin/syncopated-audit-warn. auditd runs it
# (space_left_action = exec) when free space on /var/log/audit drops below
# space_left; syncopated-audit-check.timer runs it at boot and every hour, so
# the warning appears after a reboot and clears once space is back.
#
# Below the threshold it
#   - logs a warning-priority journal entry (tag syncopated-audit),
#   - writes /etc/motd.d/90-syncopated-audit (shell logins) and
#     /etc/cockpit/issue.cockpit (Cockpit login banner; cockpit.conf points
#     Banner= at it),
#   - writes the state file read by syncopated-audit-notify, and shows the
#     GNOME critical notification to logged-in wheel users when the condition
#     starts. syncopated-audit-notify repeats it at every login.
# At or above the threshold it removes those files again.
#
# Settings: /etc/sysconfig/syncopated-audit-warn (WARN_FREE_PERCENT). The SYNC_*
# variables point paths elsewhere for tests.
set -uo pipefail

CONF=${SYNC_AUDIT_CONF:-/etc/sysconfig/syncopated-audit-warn}
AUDIT_DIR=${SYNC_AUDIT_DIR:-/var/log/audit}
STATE=${SYNC_AUDIT_STATE:-/run/syncopated/audit-space-low}
MOTD=${SYNC_AUDIT_MOTD:-/etc/motd.d/90-syncopated-audit}
COCKPIT=${SYNC_AUDIT_COCKPIT:-/etc/cockpit/issue.cockpit}
NOTIFY=${SYNC_AUDIT_NOTIFY:-/usr/local/bin/syncopated-audit-notify}
LOGGER=${SYNC_AUDIT_LOGGER:-logger}
RUN_DIR=${SYNC_AUDIT_RUN_DIR:-/run/user}

WARN_FREE_PERCENT=25
# shellcheck source=/dev/null
[ -r "$CONF" ] && . "$CONF"

# Percent of the volume that is free, and its size in MiB.
read -r size_k avail_k < <(df -Pk "$AUDIT_DIR" 2>/dev/null | awk 'NR == 2 { print $2, $4 }')
if [ -z "${size_k:-}" ] || [ "$size_k" -eq 0 ]; then
  "$LOGGER" -t syncopated-audit -p user.err "cannot read free space of $AUDIT_DIR"
  exit 1
fi
free=$((avail_k * 100 / size_k))
used=$((100 - free))

message="The audit log volume $AUDIT_DIR is ${used}% full (${free}% free, warning below ${WARN_FREE_PERCENT}%). auditd keeps working and rotates out its oldest logs. If you do not need old audit records, remove /var/log/audit/audit.log.[0-9]* (sudo), or ship them to a log host (remote_logging)."

if [ "$free" -lt "$WARN_FREE_PERCENT" ]; then
  new=0
  [ -e "$STATE" ] || new=1
  "$LOGGER" -t syncopated-audit -p user.warning "$message"
  mkdir -p "$(dirname "$STATE")" "$(dirname "$MOTD")"
  printf '%s\n' "$message" >"$STATE"
  chmod 0644 "$STATE"
  printf '\n*** WARNING: %s\n\n' "$message" >"$MOTD"
  if [ -d "$(dirname "$COCKPIT")" ]; then
    printf 'WARNING: %s\n' "$message" >"$COCKPIT"
  fi
  # Tell wheel users who are logged in now; later logins run the notifier
  # from /etc/xdg/autostart.
  if [ "$new" = 1 ] && [ -x "$NOTIFY" ]; then
    for bus in "$RUN_DIR"/*/bus; do
      [ -S "$bus" ] || continue
      uid=$(basename "$(dirname "$bus")")
      user=$(id -nu "$uid" 2>/dev/null) || continue
      id -nG "$user" 2>/dev/null | grep -qw wheel || continue
      runuser -u "$user" -- env DBUS_SESSION_BUS_ADDRESS="unix:path=$bus" "$NOTIFY" >/dev/null 2>&1 || true
    done
  fi
else
  if [ -e "$STATE" ]; then
    "$LOGGER" -t syncopated-audit -p user.notice "The audit log volume $AUDIT_DIR is back to ${free}% free; warning cleared."
  fi
  rm -f "$STATE" "$MOTD"
  if [ -e "$COCKPIT" ] && grep -q 'audit log volume' "$COCKPIT"; then
    rm -f "$COCKPIT"
  fi
fi
exit 0
