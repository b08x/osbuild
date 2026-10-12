# Verification: standalone workstation hardening

Each accepted fact in [facts.md](facts.md), where it is implemented, and what
verifies it. Status:

- **verified** — covered by a test that ran and passed in the development
  environment (Ubuntu 24.04 container, ansible-core 2.21, ansible.utils 6.1,
  pykickstart, oscap 1.3.9 with the RHEL 9 SSG data stream, auditd 3.1.2,
  systemd-journal-remote 255).
- **build host** — needs image-builder and the distribution repositories
  (gir/tinybot); the test exists and skips elsewhere. Fedora/Rocky
  repositories, quay.io and GitHub downloads were blocked by the development
  environment's egress policy, and it has no KVM.
- **hardware** — needs the physical test laptop.

Test commands: `python3 -m pytest tests`, `bats -r roles/osbuild/tests`
(firstboot as a non-root user), `ansible-lint`, `shellcheck`, the role's
`validate_*.yml` playbooks. See SKILL.md section 5.

## Audit policy and OpenSCAP

| # | Fact | Implementation | Verification | Status |
|---|---|---|---|---|
| 1 | CIS/PCI auditd.conf: rotate, 32 MB × 16 | `defaults/main.yml` `osbuild_audit_policy`, `templates/auditd.conf.j2` | `test_intent.py::test_auditd_conf_rotates_and_never_halts`; real auditd parsed and started with the rendered file | verified |
| 2 | HIPAA: rotate, 64 MB × 32 | same | same | verified |
| 3 | No single/halt/suspend; admin_space_left/disk_full rotate, disk_error syslog, space_left exec | `templates/auditd.conf.j2` | `test_auditd_conf_rotates_and_never_halts`; `tests/vm/run-install-test.sh` offline check | verified (template); build host (installed system) |
| 4 | CIS/PCI drop dac_modification_* and file_deletion_events_*; HIPAA keeps every audit rule | `openscap_unselected` in `files/rocky/10/x86_64/components/openscap-*.yml` | `test_tailoring_unselects_the_audit_deviations`; `test_openscap_tailoring.py::test_tailoring_removes_every_selected_halt_or_retention_rule` (against SSG profiles) | verified (RHEL 9 SSG; RHEL 10 on build host) |
| 5 | Deviations via tailoring, not %post; tailored scan shows them not selected | `templates/blueprint-components.toml.j2` `[customizations.openscap.tailoring]` | `test_no_post_override_of_audit_settings`; `test_syncopated_scan_reports_tailored_rules_as_not_selected` (oscap + autotailor run, ARF `notselected`); `test_manifest.py` (autotailor stage) | verified; manifest: build host |
| 6 | /var/log/audit separate nodev,nosuid,noexec; 4 GiB CIS/PCI, 10 GiB HIPAA | `filter_plugins/disk_layout.py`, `tasks/disk_layout.yml` | `test_layout_has_fixed_sizes_from_the_declared_disk`, `test_disk_sizing.py` | verified |
| 7 | <25% free: journal warning, motd/Cockpit line, persistent GNOME notification for wheel at each login | `files/scripts/syncopated-audit-{warn,notify}.sh`, `files/hardening/*` | `roles/osbuild/tests/hardening/audit-warn.bats` (10 tests) | verified (scripts); GNOME session on hardware |
| 8 | 48 h on the test laptop under cap, no halt | — | README "Acceptance: 48-hour burn-in" procedure | **hardware — not done** |
| 13 | `syncopated-scan`: stock + tailored, HTML and ARF in /var/lib/syncopated/scans/<ts>/ | `files/scripts/syncopated-scan.sh`, `/etc/syncopated/scan.conf` | `test_syncopated_scan_reports_tailored_rules_as_not_selected` (real oscap run) | verified |

## Remote logging

| # | Fact | Implementation | Verification | Status |
|---|---|---|---|---|
| 9 | Default off: upload disabled, CIS rule unselected | `tasks/hardening.yml` | `test_remote_logging_off_disables_upload_and_unselects_its_cis_rule` | verified |
| 10 | `enabled: true` + url/certs is the only change for mTLS upload | `tasks/hardening.yml`, `templates/systemd/journal-upload*.j2` | `test_remote_logging_on_is_one_switch`, `test_remote_logging_works_without_hardening` | verified |
| 11 | A systemd-journal-remote container receives journal and audit entries from a VM built with it | — | `test_journal_remote_e2e.py`: a real systemd-journal-remote receives an ordinary and an audit entry over TLS from systemd-journal-upload configured from the generated files; a log host with a foreign certificate is refused. Client-certificate enforcement skips where journal-remote lacks `--trust` (Ubuntu) | verified (process level); VM: build host |
| 12 | Unreachable log host: workstation unaffected, failure logged | service drop-in `Restart=always`, `StartLimitIntervalSec=0` | `test_an_unreachable_log_host_fails_fast_and_only_logs` | verified (uploader); VM: build host |

## Intent and playbook

| # | Fact | Implementation | Verification | Status |
|---|---|---|---|---|
| 14 | schema/intent.schema.json; build.yml validates first with ansible.utils.validate, names the field | `schema/intent.schema.json`, `tasks/intent.yml`, `playbooks/build.yml` | `test_schema_rejects_bad_intents_naming_the_field` (19 cases), `test_play_validates_before_anything_else_and_names_the_fields`, `test_build_playbook_validates_first` | verified |
| 15 | Intent v1 fields | schema | `test_example_intents_validate` | verified |
| 16 | `build.yml -e @profiles/<name>.yml` generates blueprint + build script for any ISO | `playbooks/build.yml`; `tests/generate.yml` runs the same role tasks locally | every example generated in `test_intent.py`; full play: build host | verified (generation); build host (play pre-tasks) |
| 17 | profiles/ gitignored except examples | `.gitignore` | `test_profiles_are_gitignored_except_examples` | verified |
| 18 | Former hard rules derived by the role | `tasks/intent.yml`, `tasks/hardening.yml`, `tasks/disk_layout.yml`, `tasks/blueprint.yml` | `test_extra_repos_come_from_components`, cuda `/usr` checks, conflict assert in `validate_kickstart_injection.yml` | verified |
| 19 | Example per ISO playbook, blueprint matches apart from intended changes; ISO playbooks deleted, container/bootc untouched | `profiles/examples/`, baselines in `baseline/` | `test_intent_parity.py` (9 examples), `test_every_iso_variant_has_an_example_and_no_iso_playbook_is_left`, `test_iso_builds_only_go_through_build_yml` | verified |
| 20 | Every example passes `image-builder manifest` depsolve | — | `tests/test_manifest.py` | **build host — not run here** |
| 21 | Skill tells the agent to write an intent | `.claude/skills/syncopated/SKILL.md`, `.agents/...` | review | verified |

## Disk

| # | Fact | Implementation | Verification | Status |
|---|---|---|---|---|
| 22 | Sizes computed at generation, fixed logvol sizes; no min/max/weight in %pre | `filter_plugins/disk_layout.py`, `templates/kickstart.toml.j2`, `files/kickstart/syncopated.ks` | `test_disk_sizing.py` (pins the old %pre results), `kickstart.bats` "%pre computes no volume sizes" | verified |
| 23 | Larger disk → /home; smaller → abort naming both sizes | `syncopated.ks` %pre | `kickstart.bats` (surplus, no-/home, too-small cases) | verified |
| 24 | none → simple layout; hardened → compliant | `tasks/disk_layout.yml` | `test_layout_has_fixed_sizes_from_the_declared_disk` | verified |
| 25 | Disk selection unchanged | `syncopated.ks` %pre | `kickstart.bats` (10 selection tests carried over) | verified |
| 26 | 30 s tty countdown naming model and size; key aborts, timeout proceeds | `syncopated.ks` %pre (tty8) | `kickstart.bats` countdown tests | verified (stubbed tty); real console: build host |
| 27 | disk.serial mismatch aborts before touching a disk | `syncopated.ks` %pre | `kickstart.bats` serial tests | verified |
| 28 | Sizing unit tests at minimum, typical, large | — | `test_disk_sizing.py` | verified |

## Unattended install and credentials

| # | Fact | Implementation | Verification | Status |
|---|---|---|---|---|
| 29 | Install asks nothing (LUKS passphrase only) | `templates/kickstart.toml.j2` | `test_install_asks_nothing`; `tests/vm/run-install-test.sh` | verified (kickstart); VM: build host |
| 30 | New random password per generation; hash only in blueprint/ISO; plaintext printed once and in a 0600 file | `tasks/credentials.yml`, `tasks/blueprint.yml`, `tasks/main.yml` | `test_only_the_hash_reaches_the_blueprint` (passlib verify), `test_each_generation_makes_a_new_password`, `test_outputs_are_mode_0600` | verified |
| 31 | chage -d 0, GDM asks | kickstart %post | `test_install_asks_nothing`; VM offline check of /etc/shadow | verified (kickstart); GDM: hardware |
| 32 | rootpw --lock | kickstart | `test_install_asks_nothing`; VM offline check | verified (kickstart) |
| 33 | Groups: wheel + component user_groups + intent groups | `user_groups` in components, `tasks/credentials.yml` | `test_user_groups_come_from_wheel_components_and_intent` | verified |
| 34 | Optional uid and ssh_pubkey | kickstart `user --uid`, `sshkey` | same | verified |
| 35 | .toml, build-*.sh, ISO, password file 0600; no LUKS passphrase in any file | `tasks/blueprint.yml`, `tasks/main.yml`, `image-builder-build.sh.j2` (`chmod 0600` ISO) | `test_outputs_are_mode_0600`, `test_iso_is_made_0600_by_the_build_script`, `test_no_luks_passphrase_anywhere` | verified (ISO chmod: build host) |
| 36 | Fails early without passlib | `tasks/passlib.yml` (run right after validation) | `test_missing_passlib_fails_early_with_a_clear_message` | verified |
| 37 | Kickstart of every example passes ksvalidator -v RHEL10 | — | `test_kickstart_passes_ksvalidator_rhel10` (layout filled in), `validate_kickstart_injection.yml` | verified |
| 38 | Unattended QEMU/libvirt install of the CIS ISO; layout, auditd.conf, syncopated-scan checked | `tests/vm/run-install-test.sh`, `tests/test_vm_install.py` | needs the ISO and /dev/kvm | **build host — not run here** |

## Open items

1. Run `python3 -m pytest tests/test_manifest.py` on gir (fact 20; also confirms
   the RHEL 10 rule IDs, including `service_systemd-journal-upload_enabled`,
   reach autotailor).
2. Build the CIS example ISO and run
   `SYNCOPATED_VM_ISO=<iso> python3 -m pytest tests/test_vm_install.py -s` on a
   KVM host (facts 3, 11, 12, 26, 29, 31, 32, 38 on a real system).
3. 48-hour burn-in on the test laptop (fact 8), procedure in README.md.
4. Watch: the HIPAA stock profile keeps `audit_rules_system_shutdown`
   (`-f 2`, kernel panic on an audit failure) because fact 4 keeps every
   HIPAA audit rule. With rotating disk actions a full audit volume no longer
   triggers it, but an audit backlog overflow still could. If that is
   unwanted, set the failure mode to printk in the tailoring.
