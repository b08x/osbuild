#!/usr/bin/bash
# syncopated-audit-notify: GNOME critical notification while the audit log
# volume is nearly full.
#
# Installed as /usr/local/bin/syncopated-audit-notify and started at every
# graphical login by /etc/xdg/autostart/syncopated-audit-notify.desktop;
# syncopated-audit-warn also runs it in the sessions of logged-in wheel users
# when the condition starts. It shows nothing to users outside wheel or while
# the volume has space (no state file from syncopated-audit-warn). Critical
# notifications stay on screen until dismissed.
set -uo pipefail

STATE=${SYNC_AUDIT_STATE:-/run/syncopated/audit-space-low}

id -nG | grep -qw wheel || exit 0
[ -s "$STATE" ] || exit 0
body=$(head -c 1000 "$STATE")
title="Audit log space is running low"

if command -v gdbus >/dev/null 2>&1; then
  # Notify(app_name, replaces_id, app_icon, summary, body, actions, hints, timeout)
  # urgency 2 = critical; timeout 0 = never expire.
  gdbus call --session \
    --dest org.freedesktop.Notifications \
    --object-path /org/freedesktop/Notifications \
    --method org.freedesktop.Notifications.Notify \
    "Syncopated" 0 "dialog-warning" "$title" "$body" "[]" \
    "{'urgency': <byte 2>, 'resident': <true>}" 0 >/dev/null && exit 0
fi
if command -v notify-send >/dev/null 2>&1; then
  exec notify-send --urgency=critical --app-name=Syncopated --icon=dialog-warning "$title" "$body"
fi
exit 1
