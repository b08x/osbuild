#!/usr/bin/bash
# syncopated-scan: evaluate this host against the stock OpenSCAP profile and
# the workstation-tailored profile it was built with.
#
#   sudo syncopated-scan
#
# Writes, into /var/lib/syncopated/scans/<timestamp>/:
#   stock-arf.xml     stock-report.html     stock.log
#   tailored-arf.xml  tailored-report.html  tailored.log
#   tailoring.xml (copy of the tailoring used)   summary.txt
# The stock scan lists the workstation deviations (audit retention, actions,
# desktop noise rules) as failures; the tailored scan lists them as not
# selected. Exit status 0 when both evaluations ran (rule failures included),
# 1 on an error.
#
# Settings: /etc/syncopated/scan.conf (written by the osbuild role):
#   DATASTREAM        SCAP source data stream
#   PROFILE           stock profile ID
#   TAILORING_FILES   candidate tailoring files written by image-builder
#   UNSELECTED        rule IDs the tailoring unselects; used to rebuild the
#                     tailoring with autotailor when no candidate exists
set -uo pipefail

CONF=${SYNC_SCAN_CONF:-/etc/syncopated/scan.conf}
OUT_ROOT=${SYNC_SCAN_DIR:-/var/lib/syncopated/scans}
OSCAP=${SYNC_SCAN_OSCAP:-oscap}
AUTOTAILOR=${SYNC_SCAN_AUTOTAILOR:-autotailor}

die() {
  echo "syncopated-scan: $*" >&2
  exit 1
}

DATASTREAM=
PROFILE=
TAILORING_FILES=
UNSELECTED=
# shellcheck source=/dev/null
[ -r "$CONF" ] && . "$CONF"
if [ -z "$DATASTREAM" ] || [ -z "$PROFILE" ]; then
  die "$CONF must set DATASTREAM and PROFILE"
fi
[ -r "$DATASTREAM" ] || die "data stream $DATASTREAM not found (package scap-security-guide)"
[ "${SYNC_SCAN_ANY_USER:-0}" = 1 ] || [ "$(id -u)" -eq 0 ] || die "run as root (sudo syncopated-scan)"
command -v "$OSCAP" >/dev/null 2>&1 || die "oscap not found (package openscap-scanner)"

out=$OUT_ROOT/$(date +%Y%m%dT%H%M%S)
mkdir -p "$OUT_ROOT" || die "cannot create $OUT_ROOT"
mkdir -m 0700 "$out" || die "cannot create $out"

tailoring=
for f in $TAILORING_FILES; do
  if [ -r "$f" ]; then
    tailoring=$f
    break
  fi
done
if [ -n "$tailoring" ]; then
  cp "$tailoring" "$out/tailoring.xml"
elif command -v "$AUTOTAILOR" >/dev/null 2>&1; then
  args=()
  for rule in $UNSELECTED; do
    args+=(--unselect "$rule")
  done
  "$AUTOTAILOR" --new-profile-id "${PROFILE}_syncopated_tailoring" "${args[@]}" \
    -o "$out/tailoring.xml" "$DATASTREAM" "$PROFILE" ||
    die "autotailor could not rebuild the tailoring"
else
  die "no tailoring file (looked for: $TAILORING_FILES) and no autotailor to rebuild it (package openscap-utils)"
fi
tailored_profile=$(grep -o 'Profile id="[^"]*"' "$out/tailoring.xml" | head -n1 | cut -d'"' -f2)
[ -n "$tailored_profile" ] || die "$out/tailoring.xml names no profile"

# eval NAME OSCAP-ARGS...: oscap exits 0 (all pass) or 2 (some rules failed)
# after a complete evaluation; anything else is an error.
eval_profile() {
  local name=$1 rc
  shift
  "$OSCAP" xccdf eval "$@" \
    --results-arf "$out/$name-arf.xml" --report "$out/$name-report.html" \
    "$DATASTREAM" >"$out/$name.log" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
    echo "syncopated-scan: $name evaluation failed (oscap exit $rc), see $out/$name.log" >&2
    return 1
  fi
  {
    printf '%s profile:' "$name"
    awk '/^Result/ { n[$2]++ } END { for (r in n) printf " %s=%d", r, n[r]; print "" }' "$out/$name.log"
  } >>"$out/summary.txt"
}

status=0
eval_profile stock --profile "$PROFILE" || status=1
eval_profile tailored --tailoring-file "$out/tailoring.xml" --profile "$tailored_profile" || status=1

echo "Reports in $out:"
cat "$out/summary.txt" 2>/dev/null
ls -1 "$out"
exit "$status"
