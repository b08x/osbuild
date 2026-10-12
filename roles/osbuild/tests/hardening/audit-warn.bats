#!/usr/bin/env bats
# Tests for files/scripts/syncopated-audit-warn.sh and
# files/scripts/syncopated-audit-notify.sh. The SYNC_AUDIT_* variables move
# every path into the test directory; WARN_FREE_PERCENT 101 forces the
# low-space condition on any volume and 0 clears it.

setup() {
  SCRIPTS="$(cd "$BATS_TEST_DIRNAME/../../files/scripts" && pwd)"
  export SYNC_AUDIT_CONF="$BATS_TEST_TMPDIR/audit-warn.conf"
  export SYNC_AUDIT_DIR="$BATS_TEST_TMPDIR"
  export SYNC_AUDIT_STATE="$BATS_TEST_TMPDIR/run/audit-space-low"
  export SYNC_AUDIT_MOTD="$BATS_TEST_TMPDIR/motd.d/90-syncopated-audit"
  mkdir -p "$BATS_TEST_TMPDIR/cockpit"
  export SYNC_AUDIT_COCKPIT="$BATS_TEST_TMPDIR/cockpit/issue.cockpit"
  export SYNC_AUDIT_RUN_DIR="$BATS_TEST_TMPDIR/run-user"
  mkdir -p "$SYNC_AUDIT_RUN_DIR"
  export SYNC_AUDIT_NOTIFY="$BATS_TEST_TMPDIR/no-notify"
  export LOG="$BATS_TEST_TMPDIR/logger.log"
  export SYNC_AUDIT_LOGGER="$BATS_TEST_TMPDIR/logger"
  printf '#!/bin/sh\necho "$@" >>"%s"\n' "$LOG" >"$SYNC_AUDIT_LOGGER"
  chmod +x "$SYNC_AUDIT_LOGGER"
}

warn_below() {
  echo "WARN_FREE_PERCENT=$1" >"$SYNC_AUDIT_CONF"
}

@test "below the threshold: warning-priority journal entry, motd, Cockpit banner and state" {
  warn_below 101
  run bash "$SCRIPTS/syncopated-audit-warn.sh"
  [ "$status" -eq 0 ]
  grep -q -- "-t syncopated-audit -p user.warning The audit log volume $SYNC_AUDIT_DIR is" "$LOG"
  grep -q "WARNING: The audit log volume" "$SYNC_AUDIT_MOTD"
  grep -q "WARNING: The audit log volume" "$SYNC_AUDIT_COCKPIT"
  grep -q "warning below 101%" "$SYNC_AUDIT_STATE"
  [ "$(stat -c %a "$SYNC_AUDIT_STATE")" = 644 ]
}

@test "the message says auditd keeps working and how to clear space" {
  warn_below 101
  run bash "$SCRIPTS/syncopated-audit-warn.sh"
  grep -q "auditd keeps working and rotates out its oldest logs" "$SYNC_AUDIT_STATE"
  grep -q "remove /var/log/audit/audit.log" "$SYNC_AUDIT_STATE"
}

@test "warns again on every run while the condition holds" {
  warn_below 101
  bash "$SCRIPTS/syncopated-audit-warn.sh"
  bash "$SCRIPTS/syncopated-audit-warn.sh"
  [ "$(grep -c user.warning "$LOG")" -eq 2 ]
}

@test "above the threshold after a warning: everything is cleared and the recovery is logged" {
  warn_below 101
  bash "$SCRIPTS/syncopated-audit-warn.sh"
  warn_below 0
  run bash "$SCRIPTS/syncopated-audit-warn.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$SYNC_AUDIT_STATE" ]
  [ ! -e "$SYNC_AUDIT_MOTD" ]
  [ ! -e "$SYNC_AUDIT_COCKPIT" ]
  grep -q "user.notice .*warning cleared" "$LOG"
}

@test "above the threshold with no prior warning: silent" {
  warn_below 0
  run bash "$SCRIPTS/syncopated-audit-warn.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$LOG" ]
}

@test "a Cockpit banner written by someone else is left alone" {
  warn_below 0
  echo "Authorized use only" >"$SYNC_AUDIT_COCKPIT"
  run bash "$SCRIPTS/syncopated-audit-warn.sh"
  grep -q "Authorized use only" "$SYNC_AUDIT_COCKPIT"
}

@test "an unreadable volume is an error in the journal, not a crash" {
  export SYNC_AUDIT_DIR="$BATS_TEST_TMPDIR/does-not-exist"
  run bash "$SCRIPTS/syncopated-audit-warn.sh"
  [ "$status" -eq 1 ]
  grep -q "user.err cannot read free space" "$LOG"
}

# notifier: id and gdbus are stubbed through PATH
notify_env() {
  STUBS="$BATS_TEST_TMPDIR/stubs"
  mkdir -p "$STUBS"
  printf '#!/bin/sh\necho "%s"\n' "$1" >"$STUBS/id"
  printf '#!/bin/sh\nprintf "%%s\\n" "$@" >"%s"\n' "$BATS_TEST_TMPDIR/gdbus.args" >"$STUBS/gdbus"
  chmod +x "$STUBS/id" "$STUBS/gdbus"
  export PATH="$STUBS:$PATH"
}

@test "notifier: wheel user with the condition gets a critical, non-expiring notification" {
  notify_env "users wheel"
  mkdir -p "$(dirname "$SYNC_AUDIT_STATE")"
  echo "The audit log volume /var/log/audit is 80% full" >"$SYNC_AUDIT_STATE"
  run bash "$SCRIPTS/syncopated-audit-notify.sh"
  [ "$status" -eq 0 ]
  grep -qx "org.freedesktop.Notifications.Notify" "$BATS_TEST_TMPDIR/gdbus.args"
  grep -qx "Audit log space is running low" "$BATS_TEST_TMPDIR/gdbus.args"
  grep -q "'urgency': <byte 2>" "$BATS_TEST_TMPDIR/gdbus.args"
  grep -qx "80% full" <(grep -o "80% full" "$BATS_TEST_TMPDIR/gdbus.args")
}

@test "notifier: users outside wheel see nothing" {
  notify_env "users audio"
  mkdir -p "$(dirname "$SYNC_AUDIT_STATE")"
  echo "low" >"$SYNC_AUDIT_STATE"
  run bash "$SCRIPTS/syncopated-audit-notify.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$BATS_TEST_TMPDIR/gdbus.args" ]
}

@test "notifier: nothing while the volume has space" {
  notify_env "users wheel"
  run bash "$SCRIPTS/syncopated-audit-notify.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$BATS_TEST_TMPDIR/gdbus.args" ]
}
