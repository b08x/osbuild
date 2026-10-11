# Grill notes — standalone-workstation-hardening

## Root cause (traced)
- `/var/log/audit` fills because CIS L2 (`cis_workstation_l2`, ssg-rhel10) sets
  `max_log_file_action = keep_logs` (never delete) with `max_log_file = 8`, and
  `admin_space_left_action`/`disk_full_action` = `single|halt`. No repo override exists;
  `openscap-cis-l2-workstation.toml` only sets `profile_id`.
- Fill rate: 95 audit rules; desktop-noisy syscall rules (dac_modification_*,
  file_deletion_events_*, unsuccessful_file_modification_*) suspected. User declined
  aureport confirmation — fix is policy-level regardless of which rule dominates.

## Decisions
1. Audit records are NOT kept for history on a standalone workstation. Retention that
   matters belongs on a remote log server; keep_logs here is security theater that
   breaks the machine.
2. A full audit volume must never halt or single-user the system.
3. A persistent, user-visible warning is shown when the audit volume is nearly full
   ("clear it if you don't need it").
4. User does not want to author install facts in two places (blueprint + kickstart).
