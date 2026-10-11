# Implementation Plan: Standalone Workstation Hardening

## Overview
Transform the appliance build workflow into an intent-driven, unattended ISO generation pipeline that enforces enterprise OpenSCAP security standards tailored for standalone workstations. Sizing calculations move from installer runtime to image generation time; audit logging is prevented from overflowing storage or halting the workstation; credentials are generated securely without interactive installer prompts; and configuration intent is centralized in a validated JSON schema.

---

## Order of Operations

### Step 1: OpenSCAP Tailoring & Audit Policy Overrides
Implement OpenSCAP tailoring support in `roles/osbuild` to adjust audit settings without marking audit rules as failures in compliance scans.

- **Files touched:**
  - `roles/osbuild/files/rocky/10/x86_64/components/openscap-cis-l2-workstation.toml`
  - `roles/osbuild/files/rocky/10/x86_64/components/openscap-pci-dss.toml`
  - `roles/osbuild/files/rocky/10/x86_64/components/openscap-hipaa.toml`
  - `roles/osbuild/templates/auditd.conf.j2`
  - `roles/osbuild/files/scripts/syncopated-audit-warn.sh`
  - `roles/osbuild/files/scripts/syncopated-scan.sh`
  - `roles/osbuild/tasks/blueprint.yml`
- **Actions:**
  - Add `[customizations.openscap.tailoring]` with `unselected` lists to `openscap-cis-l2-workstation.toml` and `openscap-pci-dss.toml`, deselecting noisy desktop rules (`dac_modification_*`, `file_deletion_events_*`), halts/singles (`auditd_data_disk_full_action`, `auditd_data_retention_admin_space_left_action`, `auditd_data_disk_error_action`), and `auditd_data_retention_max_log_file_action`.
  - For `openscap-hipaa.toml`, keep all audit logging rules selected while unselecting only the halt/single/suspend action rules.
  - Add template `auditd.conf.j2` configuring log rotation (`max_log_file_action = rotate`, `max_log_file = 32`, `num_logs = 16` for CIS/PCI; `max_log_file = 64`, `num_logs = 32` for HIPAA; actions set to rotate, syslog, and exec warning script).
  - Implement `/usr/local/libexec/syncopated-audit-warn` to emit a journal warning, set a persistent motd/Cockpit banner, and trigger a persistent GNOME critical notification for `wheel` users when audit space drops below 25%.
  - Implement `/usr/local/bin/syncopated-scan` to run `oscap xccdf eval` against both stock and tailored profiles, outputting ARF and HTML reports into `/var/lib/syncopated/scans/<timestamp>/`.
- **Verification:**
  - `image-builder manifest image-installer --distro rocky-10.2 --arch x86_64 --blueprint <rendered_bp>` outputs valid manifests containing `org.osbuild.oscap.autotailor` and `org.osbuild.oscap.remediation`.
  - Automated tests verifying tailored unselected rules and auditd parameters.

---

### Step 2: Generation-Time Disk Sizing & Unattended Kickstart Refactoring
Shift partition and volume calculations from `%pre` bash scripts to playbook generation time.

- **Files touched:**
  - `roles/osbuild/tasks/disk_layout.yml` (new task file)
  - `roles/osbuild/templates/kickstart.toml.j2`
  - `roles/osbuild/files/kickstart/syncopated.ks`
  - `roles/osbuild/tests/kickstart/kickstart.bats`
- **Actions:**
  - Compute volume sizes at playbook execution time based on `disk.size_gib`:
    - Hardened profiles: fixed root (35 GiB), `/usr` (80 GiB when nvidia/cuda selected, else 45 GiB), `/var/tmp` (8 GiB), `/var/log` (10 GiB), `/var/log/audit` (4 GiB for CIS/PCI, 10 GiB for HIPAA), `/tmp` (8 GiB lv if tmp=lv, else tmpfs), `/var` (40 GiB min), and `/home` absorbing remaining space via `--grow`.
    - `hardening: none`: standard workstation layout (`/`, `/usr`, `/var`, `/home` with `--grow`).
  - Render exact `logvol` directives directly into `kickstart.toml.j2`.
  - Streamline `syncopated.ks`:
    - Retain automated target drive discovery (skip install media, USB, read-only, removable; prioritize NVMe, then largest).
    - Insert 30-second countdown on tty1 displaying target drive model and capacity; any key aborts install, timeout continues.
    - Check target drive capacity against required minimum and verify `disk.serial` if configured in intent; abort on mismatch.
    - Remove runtime weight/partitioning computation from `%pre`.
- **Verification:**
  - Sizing math test suite in `tests/test_disk_sizing.py` and `kickstart.bats` testing minimum, average, and high-capacity disks.
  - `ksvalidator -v RHEL10` validates rendered kickstart syntax.

---

### Step 3: User Accounts, Credentials & Permissions Hardening
Eliminate installer user prompts by generating throwaway credentials at build time with forced change on first login.

- **Files touched:**
  - `roles/osbuild/tasks/credentials.yml` (new task file)
  - `roles/osbuild/tasks/components.yml`
  - `roles/osbuild/templates/kickstart.toml.j2`
  - `roles/osbuild/tasks/blueprint.yml`
  - `roles/osbuild/files/*/*/components/*.yml` (add optional `user_groups` field)
- **Actions:**
  - Add assertion verifying `passlib` is present on controller host.
  - Generate a secure random password on the controller, calculate SHA-512 crypt hash, and inject `user --name ... --groups ... --iscrypted --password ...` into the kickstart.
  - Include `rootpw --lock` in kickstart.
  - Append `chage -d 0 <user>` in kickstart `%post` so GDM prompts for password change on initial login.
  - Update `components.yml` to collect optional `user_groups` from selected components (e.g., `libvirt` from `containers-virt`) and union them with `wheel` and user-specified groups.
  - Write temporary cleartext password to mode `0600` file `{{ osbuild_output_dir }}/{{ osbuild_blueprint_name }}.credentials.txt` and print in a play summary banner.
  - Ensure mode `0600` is enforced on generated `.toml`, `build-*.sh`, and output credentials.
- **Verification:**
  - Pytest checking group aggregation from component definitions.
  - Tests ensuring permissions on generated files are strictly `0600` and no LUKS passphrase or cleartext password is stored in blueprints.

---

### Step 4: Remote Logging Toggle (mTLS via systemd-journal-upload)
Provide a clean boolean switch for remote log transmission without breaking standalone installations.

- **Files touched:**
  - `roles/osbuild/templates/systemd/journal-upload.conf.j2`
  - `roles/osbuild/tasks/blueprint.yml`
  - `roles/osbuild/files/rocky/10/x86_64/components/openscap-cis-l2-workstation.toml`
- **Actions:**
  - Default `remote_logging.enabled` to `false`. When false, deselect `service_systemd-journal-upload_enabled` in OpenSCAP tailoring and mask/disable the unit.
  - When `true`, render `/etc/systemd/journal-upload.conf` with provided `url`, CA, and client certificates; enable `systemd-journal-upload.service`.
  - Ensure failure to contact the remote log server does not block local log persistence or affect system operation.
- **Verification:**
  - Unit test verifying tailoring and config rendering when `remote_logging.enabled` is false vs true.
  - Integration test (`tests/test_journal_remote_e2e.py`) starting a local `systemd-journal-remote` test container, transmitting test journal records, and verifying reception.

---

### Step 5: Intent Schema Definition & Single Universal Playbook
Create a single entry point for image generation driven by a formal specification.

- **Files touched:**
  - `schema/intent.schema.json` (new JSON schema)
  - `playbooks/build.yml` (new single universal entry playbook)
  - `.gitignore` (ignore `profiles/` except `profiles/examples/`)
  - `profiles/examples/*.yml` (convert existing ISO playbooks to example intents)
  - Remove redundant ISO playbooks (`playbooks/osbuild-rocky-iso-*.yml`, `playbooks/osbuild-almalinux-iso*.yml`)
- **Actions:**
  - Define `schema/intent.schema.json` covering: `distro`, `arch`, `hostname`, `components`, `hardening`, `disk`, `users`, `locale`, `remote_logging`, `extra_packages`, `package_pins`.
  - In `playbooks/build.yml`, validate input variables against `schema/intent.schema.json` using `ansible.utils.validate`.
  - Move build-host vs target repository rules and sizing rules previously documented in `SKILL.md` into role tasks/defaults.
  - Create example intents in `profiles/examples/` corresponding to all current ISO variants.
  - Verify manifest parity with previous playbooks, then retire old ISO playbooks.
- **Verification:**
  - `ansible-playbook playbooks/build.yml -e @profiles/examples/rocky-10-2-workstation-nvidia-cis.yml` succeeds in generate mode.
  - `image-builder manifest` depsolve passes for every example intent in `profiles/examples/`.
  - Schema validation rejects invalid intent samples with descriptive messages.

---

### Step 6: Update Skill, Documentation & Verification Suites
Update the syncopated builder skill and verify the complete workflow.

- **Files touched:**
  - `.claude/skills/syncopated/SKILL.md`
  - `.agents/skills/syncopated/SKILL.md`
  - `README.md`
  - `tests/`
- **Actions:**
  - Update `syncopated` skill documentation to guide agents to author intent files under `profiles/` instead of generating custom Ansible playbooks.
  - Update `README.md` reflecting the new intent-driven workflow, disk layout model, and credentials management.
  - Add pytest test suite covering intent validation, manifest generation, and tailoring.
  - Add unattended QEMU VM test harness to execute automated installation of the generated CIS ISO.
- **Verification:**
  - Run test suite: `pytest`, `bats roles/osbuild/tests/kickstart/kickstart.bats`, `ansible-lint`, and `shellcheck`.
  - Headless QEMU install test completes unattended; post-install inspects partition layout, `auditd.conf`, and runs `syncopated-scan`.
  - Document manual 48-hour burn-in verification on physical laptop hardware.

---

## Risks & Open Questions
1. **OpenSCAP package availability in buildroot:** Autotailoring requires `openscap-utils` in the osbuild buildroot; osbuild pulls this when `org.osbuild.oscap.autotailor` is in the pipeline. Confirmed available on Fedora 43 build host.
2. **LUKS Passphrase Entry:** As decided, LUKS passphrase will be the sole interactive prompt when encryption is enabled; unattended installs with LUKS enabled still pause once for user input unless TPM2 enrollment is added in a future enhancement.
3. **Audit Rule Volume on Workstations:** If desktop noise remains elevated after deselecting `dac_modification_*` and `file_deletion_events_*`, subsequent tailoring can deselect `unsuccessful_file_modification_*` based on real `aureport` metrics.
