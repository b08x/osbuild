# OSBuild Image Builder & Package Tracker

Dedicated repository for composing and building custom OS appliances, immutable bootc containers, and installer ISOs across **Fedora**, **AlmaLinux**, and **Rocky Linux** using Red Hat `image-builder` and `osbuild`.

## Repository Structure

```text
├── osbuild.yml                  # Root bootc / VM image playbook (= playbooks/osbuild.yml)
├── composer_cli.yml             # Alternative root build playbook (osbuild-composer daemon)
├── ansible.cfg                  # Ansible configuration
├── inventory/                   # Host inventories (builder nodes: gir, tinybot)
│   └── hosts.yml
├── playbooks/
│   ├── build.yml                # Installer ISOs: one playbook, driven by an intent
│   ├── osbuild.yml              # Host-native bootc image or VM disk image (no ISOs)
│   ├── composer_cli.yml         # Alternative daemon-driven builder playbook
│   └── osbuild-rocky-cuda-container.yml
├── schema/
│   └── intent.schema.json       # What an intent may say (validated before any task)
├── profiles/                    # Your intents (gitignored) ...
│   └── examples/                # ... and the committed examples, one per ISO variant
├── roles/                       # Standalone Ansible roles
│   ├── osbuild/                 # Primary osbuild image composer role (image-builder CLI)
│   └── composer_cli/            # Alternative composer-cli role (osbuild-composer daemon)
├── scripts/
│   └── package_tracker.py       # TUI and CLI tool for the component files' package lists
├── tests/                       # pytest suite: intents, disk sizing, tailoring, parity, remote
│                                # logging e2e, manifest (build host) and VM install (KVM)
├── requirements.txt             # Python dependencies
├── .agents/
│   └── skills/
│       └── syncopated/          # Syncopated appliance builder agent skill
└── .claude/
    └── skills/
        └── syncopated/          # Same SKILL.md, for Claude Code
```

---

## Package Tracker (`scripts/package_tracker.py`)

The component files are the only package data. A *target* is one `roles/osbuild/files/<distro>/<major>/<arch>/` directory: `rocky/10/x86_64`, `rocky/9/x86_64`, `almalinux/10/x86_64` or `fedora/43/x86_64`. The tracker lists, searches, adds and removes packages in `<target>/components/*.yml`. Edits touch only the `packages:` list of one file: comments, key order and the order of existing packages stay, and new packages are appended.

### CLI

```bash
# Components of a target, with label and package count
python3 scripts/package_tracker.py list --target rocky/10/x86_64

# Every target/component that contains a matching package
python3 scripts/package_tracker.py search nvidia

# Add packages (--verify checks the target's repos first; @groups skip the check)
python3 scripts/package_tracker.py add --target rocky/10/x86_64 base htop fastfetch --verify

# Remove packages (the last package of a component cannot be removed)
python3 scripts/package_tracker.py remove --target rocky/10/x86_64 base htop

# Audit a component, or a whole target, against the repos
python3 scripts/package_tracker.py verify --target rocky/10/x86_64 base
```

### Choosing an Intent's (or a Playbook's) Components

`playbook` edits the `components` list of an intent (`profiles/*.yml`) or the `osbuild_blueprint_components` list of a playbook without touching anything else in the file. The target comes from the file's `distro` / `osbuild_distro`.

```bash
python3 scripts/package_tracker.py playbook profiles/my-workstation.yml list
python3 scripts/package_tracker.py playbook profiles/my-workstation.yml add gui-toolkit --after fonts
python3 scripts/package_tracker.py playbook profiles/my-workstation.yml remove cockpit multimedia
```

`list` shows every component of the target with `[x]` for the selected ones. `add` refuses names that have no component file for that target, and `remove` refuses to empty the list. In the TUI, choose **Components in a playbook** for a checkbox list of playbooks and intents.

`--target` is required for every command except `search`; without it the command exits with status 2 and lists the available targets. A unique prefix such as `rocky/10` works too.

If another component of the same target already has a package, `add` prints a warning naming that component and refuses the package unless you pass `--force`.

### Interactive Mode (TUI)

```bash
python3 scripts/package_tracker.py tui
```

The TUI asks for a target only when more than one exists, then lists the components (label and package count). Choosing one opens a submenu:

- **Edit packages**: a checkbox list with every package checked. Unchecked packages are removed after a confirmation that lists them.
- **Add packages**: type names (space or comma separated), optionally verify them, and confirm when another component already has a name.
- **Show details**: label, `repo_urls`, `services`, `kernel_args` and `fragment`.
- **Back**: returns to the component list, whose own **Back** returns to the target list.

### Where Package Lists Are Defined

Component files carry all package data; static blueprints (`osbuild_static_blueprint_path`) are hand-written and outside the tracker. To add a package to every workstation build, add it to the matching component in each target that provides the name (`search` shows where a name already lives). Before adding a name, confirm the target repository provides it, or use `add --verify`:

```bash
dnf repoquery -q --repofrompath=r,<repo URL> --repo r --qf '%{name} %{repoid}\n' <package>
```

The full procedure (new repositories, removals, verification) is in [SKILL.md, section 4](.claude/skills/syncopated/SKILL.md).

---

## Building Installer ISOs from an Intent

An intent describes one workstation: distro, components (hardware and software stack), hardening profile, disk, users, locale and remote logging. `schema/intent.schema.json` defines it; `profiles/examples/` has one example per supported ISO variant.

```bash
cp profiles/examples/rocky-10-2-workstation-openscap-cis-l2-workstation.yml profiles/studio.yml
$EDITOR profiles/studio.yml                    # name, hostname, disk.size_gib, users, locale
ansible-playbook playbooks/build.yml -e @profiles/studio.yml
bash /var/tmp/osbuild-images/build-<name>.sh   # builds <name>-<commit>.iso
```

The play validates the intent before anything else and stops naming the offending field (`intent.disk.size_gib: 10 is less than the minimum of 32`). It writes, mode `0600` and owned by you:

| File | Content |
|---|---|
| `<name>.toml` | Blueprint with the kickstart: users, locked root, the disk layout |
| `build-<name>.sh` | Runs `image-builder build` with the components' extra repositories |
| `<name>.credentials.txt` | The temporary password of each user (also printed once at the end of the play) |

**The install asks nothing.** Boot the ISO and walk away: the installer picks the target disk (install media, removable, read-only and USB disks excluded; NVMe first, then the largest), shows a 30-second countdown on a console naming the disk's model, serial and size (any key aborts), and installs. The only possible prompt is the LUKS passphrase when `disk.encrypt` is true. Each user signs in with the temporary password and chooses a new one (GDM asks); root is locked, `wheel` uses sudo. A new password is generated on every run and only its SHA-512 hash reaches the ISO.

**Disk.** Volume sizes are computed when you generate, from `disk.size_gib` (declare the disk in GiB: a 512 GB disk is 476 GiB). A smaller disk aborts the install with both sizes on screen; a larger one gives the surplus to `/home`. `disk.serial` pins the install to one disk (`lsblk -dno SERIAL`). `hardening: none` gets `/`, `/usr`, `/var`, `/home`; any hardening profile gets the compliant layout with separate `/var/tmp`, `/var/log` and a `nodev,nosuid,noexec` `/var/log/audit` (4 GiB for CIS and PCI-DSS, 10 GiB for HIPAA). `nvidia`/`cuda-container` raise `/usr` to 80 GiB.

**Hardening** (`cis-l2-workstation`, `pci-dss`, `hipaa`; Rocky 10) applies the stock OpenSCAP profile at build time through a tailoring made for a standalone workstation, with no central log collector:

- auditd rotates within a fixed cap (`max_log_file` × `num_logs` = 32 MB × 16 for CIS and PCI-DSS, 64 MB × 32 for HIPAA) and never halts, suspends or drops to single-user mode: `admin_space_left_action` and `disk_full_action` rotate, `disk_error_action` logs.
- Below 25 % free on `/var/log/audit`, `syncopated-audit-warn` logs a warning to the journal, writes a motd and Cockpit banner, and shows `wheel` users a GNOME critical notification that returns at each login while the condition holds.
- CIS and PCI-DSS drop the per-syscall `dac_modification_*` and `file_deletion_events_*` rules, which fire on every file save and rename of a desktop session; HIPAA keeps every audit rule.
- The deviations are unselected in the tailoring, not overridden afterwards. `sudo syncopated-scan` evaluates the host against the stock and the tailored profile and writes HTML and ARF reports to `/var/lib/syncopated/scans/<timestamp>/`; the tailored report lists the deviations as not selected.

**Remote logging** is off by default. `remote_logging: {enabled: true, url: https://logs:19532, ca_cert, client_cert, client_key}` (PEM text or controller paths) is the only change needed to ship the journal, audit events included, with `systemd-journal-upload` over mTLS. An unreachable log host changes nothing on the workstation; the uploader logs the failure and retries every 30 s.

Build-host details an intent never sets are derived by the role: the image type, the extra repositories (Rocky CRB, Plus and RT, CUDA, ... come from the components' `repo_urls`; the build host's own repositories never reach another distribution's compose), the openscap component, `/usr` sizing for CUDA, and no blueprint user next to the kickstart. Your intents live in `profiles/` (gitignored); only `profiles/examples/` is committed. `passlib` must be importable by the controller's Python (`dnf install python3-passlib`); the play checks before anything else.

### Other Images

Containers and bootc images keep their playbooks:

```bash
# Rocky Linux 10.2 CUDA Application Container
ansible-playbook playbooks/osbuild-rocky-cuda-container.yml

# Host-native bootc container image (or -e osbuild_build_bootc=false -e osbuild_image_type=qcow2)
ansible-playbook osbuild.yml
```

### Key Role Options

| Variable | Default | Description |
|---|---|---|
| `osbuild_distro` | Auto-detected | Target OS (e.g. `fedora-43`, `rocky-10.2`, `almalinux-10.2`) |
| `osbuild_image_type` | Auto-detected | `image-installer`, `minimal-installer`, `qcow2`, `container` |
| `osbuild_only_generate` | `true` | Generates blueprint and build script without running image-builder |
| `osbuild_build_bootc` | `false` | Set `true` to build a bootc container image |
| `osbuild_blueprint_components` | per distro in `osbuild.yml` | Component files (`files/<distro>/<major>/<arch>/components/<name>.yml`) the blueprint is composed from. The only variable that selects packages; an intent sets it from `components` + `hardening` |
| `osbuild_extra_packages` | `[]` | Additional packages for component blueprints; static blueprints ignore it |

The intent maps to the remaining role variables (`osbuild_hardening`, `osbuild_disk_*`, `osbuild_users`, `osbuild_remote_logging`, ...); see `roles/osbuild/tasks/intent.yml` and the role README.

---

## Alternative Workflow: `composer_cli` (Builds Through the osbuild-composer Daemon)

In addition to the primary `osbuild` role (which invokes Red Hat's unified `image-builder` CLI directly), the repository provides `roles/composer_cli` as an alternative daemon-driven workflow.

`composer_cli` provisions the `osbuild-composer` systemd service, configures distribution repositories (RPMFusion, CRB, EPEL), deploys declarative blueprints to `/etc/osbuild-composer/blueprints/`, and uses `composer-cli` (Fedora) or `weldr-client` (EL 9/10) over the Weldr socket API.

### Execution

```bash
# Provision osbuild-composer and push blueprint to builder hosts (gir, tinybot)
ansible-playbook composer_cli.yml

# Or execute with custom parameters and start compose immediately
ansible-playbook composer_cli.yml \
  -e composer_cli_blueprint_name="workstation" \
  -e composer_cli_compose_type="qcow2" \
  -e composer_cli_start_compose=true
```

For full options and architectural comparison, see [`roles/composer_cli/README.md`](roles/composer_cli/README.md).

---

## Agent Skill

This repository includes the **Syncopated Appliance Builder Skill** at `.agents/skills/syncopated/SKILL.md`, with an identical copy at `.claude/skills/syncopated/SKILL.md` for Claude Code. Edit both copies together.

The skill turns a plain-language request into an **intent file** under `profiles/` (installer ISOs) or a playbook (containers, bootc), generates the blueprint and build script, and verifies them. It never builds the image; the final step is running the generated `build-<name>.sh`. Invoke it from Claude Code:

```text
/syncopated <request>
```

### How a Request Is Handled

1. **Clarify.** Up to three questions, asked only when the request leaves something open: image kind (installer ISO, application container, bootc image, qcow2), distro and version as `image-builder list` names it, hardware stack, hardening profile, disk size and users for ISOs.
2. **Write the intent.** Start from the closest `profiles/examples/*.yml`, save it as `profiles/<name>.yml`, and set what the request says. Containers and bootc images start from their playbooks instead.
3. **Verify.** `ansible-playbook playbooks/build.yml -e @profiles/<name>.yml` (validates the intent first), `shellcheck` on the build script, an `image-builder manifest` depsolve with `ksvalidator -v RHEL10` on the kickstart, and `ansible-lint`. The manifest RPM list is inspected, not just its exit code.
4. **Report.** The build command, where the temporary passwords are, what was verified, and what was not (no image built, no VM install test).

### Examples

Each prompt below is a starting point; the skill asks about anything the prompt leaves out.

**A new workstation ISO**

```text
/syncopated Rocky Linux 10.2 workstation ISO with NVIDIA drivers for a 1 TB NVMe laptop, user ada
```

The closest example is `profiles/examples/rocky-10-2-workstation-nvidia-components.yml`; the result is `profiles/<name>.yml` with `disk.size_gib: 931`, user `ada`, and the generated files in `/var/tmp/osbuild-images`.

**A hardened workstation**

```text
/syncopated same, hardened with CIS Level 2, pinned to the laptop's disk serial S5GXNF0R123
```

Sets `hardening: cis-l2-workstation` and `disk.serial`. The compliant disk layout, the workstation audit tailoring and `syncopated-scan` follow from the hardening profile.

**Shipping logs to a log host**

```text
/syncopated turn on remote logging to https://logs.lan:19532 with the certificates in ~/pki
```

Sets `remote_logging.enabled: true` with `url`, `ca_cert`, `client_cert` and `client_key`; nothing else changes.

**An application container**

```text
/syncopated CUDA application container on Rocky 10.2 for running PyTorch jobs
```

"Container" is ambiguous, so the skill asks whether an OCI application image or a bootc OS image is wanted. For an application container it installs `cuda-toolkit` rather than the `cuda` meta package (which would pull in the kernel module), disables the kickstart, firstboot and Flathub injection, and tags the output so the build script can `podman load` it. The host supplies the GPU driver:

```bash
podman run --device nvidia.com/gpu=all <image>
```

**Adding a package to the workstation builds**

```text
/syncopated add perl-IPC-Cmd and perl-FindBin to the default workstation packages
```

The skill searches the component files with `scripts/package_tracker.py search` for each name, confirms the target repositories provide it, and adds it to the matching component of every target that has the name. Names that exist only on some distributions are left out of the others, with a comment saying so. The commit convention is `➕ chore(packages): …`. A one-off package for one machine goes into that intent's `extra_packages` instead.

**Removing a package**

```text
/syncopated drop htop from the Rocky workstation builds
```

Removal also covers what exists only for that package: component `services:` units, `kernel_args`, fragments, and `repo_urls`. An explicit removal does not exclude a package that another package requires, so the generated RPM list is checked afterwards.

**Keeping the skill current**

```text
update the skill instructions to reflect the latest codebase @.claude/skills/syncopated/ @.agents/skills/syncopated/
```

Both copies change together, and the README table in [Where Package Lists Are Defined](#where-package-lists-are-defined) should be checked against the result.

### Verification Commands

The skill runs these before reporting; the same commands work by hand against any generated build.

```bash
ansible-playbook playbooks/build.yml -e @profiles/<name>.yml
shellcheck /var/tmp/osbuild-images/build-<name>.sh
ansible-lint

# Depsolve without building; run in bash (zsh does not word-split the repo flags)
bash -c 'image-builder manifest image-installer --distro rocky-10.2 --arch x86_64 \
  --blueprint <name>.toml --extra-repo <URL> > m.json'
```

The test suites (`python3 -m pytest tests`, `bats -r roles/osbuild/tests`, the role's `validate_*.yml` playbooks) are listed in [SKILL.md, section 5](.claude/skills/syncopated/SKILL.md), with the build-host-only manifest test and the unattended QEMU install test (`tests/vm/run-install-test.sh`).

> **Note:** `image-builder build` prints scriptlet errors from `grub2-probe` and `dracut` (no `/dev/log`, no block devices in the sandbox). These are expected; a failed osbuild stage or a non-zero exit code is the real signal.

---

## Architecture Roadmap

Installer ISOs are generated from a validated intent and install unattended, with OpenSCAP profiles tailored for standalone artist and developer workstations that have no external log server. Phases 1–4 and the remote logging switch of phase 5 are implemented (see [Building Installer ISOs from an Intent](#building-installer-isos-from-an-intent)); the remaining acceptance step is the 48-hour burn-in on the physical test laptop (below).

See the complete goal package at [`goals/standalone-workstation-hardening/goal.md`](goals/standalone-workstation-hardening/goal.md) for detailed specifications and acceptance criteria.

```
                      ┌────────────────────────────────────────┐
                      │   User / Wizard Intent Profile         │
                      │       (profiles/<machine>.yml)         │
                      └──────────────────┬─────────────────────┘
                                         │ Validates against schema/intent.schema.json
                                         ▼
                      ┌────────────────────────────────────────┐
                      │       Universal Build Playbook         │
                      │         (playbooks/build.yml)          │
                      └────────┬───────────────────────┬───────┘
                               │                       │
               Generation-Time │                       │ OpenSCAP Tailoring &
               Disk Layout     │                       │ Credentials Engine
                               ▼                       ▼
    ┌───────────────────────────────────┐    ┌───────────────────────────────────┐
    │     Deterministic Kickstart       │    │     Hardened Blueprint Recipe     │
    │  - Fixed logvol computed sizes    │    │  - Audit log rotation (capped)    │
    │  - /home takes a larger disk's    │
    │    surplus; reserve stays free    │    │  - Non-halting disk full actions  │
    │  - 30s abort countdown on a tty   │    │  - Desktop noise rules unselected │
    │  - Zero interactive spokes        │    │  - Throwaway random pass + chage  │
    └─────────────────┬─────────────────┘    └─────────────────┬─────────────────┘
                      │                                        │
                      └──────────────────┬─────────────────────┘
                                         │ image-builder compose
                                         ▼
                      ┌────────────────────────────────────────┐
                      │      Personalized Unattended ISO       │
                      │  Plug in -> auto install -> first boot │
                      └────────────────────────────────────────┘
```

### Phase 1: OpenSCAP Tailoring & Standalone Audit Policy *(implemented)*
- **Log Rotation & Retention Capping**: Replace default unbounded logging (`keep_logs`) with bounded rotation (512 MB cap for CIS/PCI, 2 GiB for HIPAA) to prevent `/var/log/audit` exhaustion.
- **Fail-Safe Workstation Execution**: Convert single-user/halt actions (`admin_space_left_action`, `disk_full_action`) to `rotate` and `syslog`, guaranteeing that log volume pressure never halts the physical machine.
- **Proactive User Warning**: Install `/usr/local/sbin/syncopated-audit-warn` to trigger persistent GNOME critical notifications for `wheel` users, motd/Cockpit banners, and prioritized journal alerts when capacity drops below 25%.
- **Desktop Noise Filtering**: Unselect high-frequency desktop syscall rules (`dac_modification_*`, `file_deletion_events_*`) for CIS L2 and PCI-DSS, while retaining full audit coverage for the HIPAA assessment profile.
- **Integrated Audit & Compliance Tooling**: Package `/usr/local/bin/syncopated-scan` to perform automated dual-profile audits (stock vs tailored) exporting HTML and ARF reports to `/var/lib/syncopated/scans/`.

### Phase 2: Generation-Time Deterministic Disk Sizing *(implemented)*
- **Predictable Volume Allocations**: Eliminate complex runtime `%pre` weight and volume calculations in Anaconda; compute exact partition and LV sizes at build time from the declared `disk.size_gib`.
- **Flexible Space Utilization**: Allocate fixed slices for `/`, `/usr`, `/var`, `/var/tmp`, `/var/log`, and `/var/log/audit`, with `/home` and `/var` sharing the rest by weight; on a disk larger than declared the surplus goes to `/home` while the reserve stays unassigned in `vg00`.
- **Safe Drive Target Selection**: Preserve automated drive discovery (NVMe-first, non-removable) while introducing a 30-second countdown on its own virtual console (tty1 belongs to Anaconda's tmux) with an instant abort key and optional drive serial number verification.

### Phase 3: Personalized, Unattended Installation & Credentials *(implemented)*
- **Zero Interactive Installer Friction**: Suppress root password, user creation, and partition spokes in Anaconda for fully unattended deployments.
- **Ephemeral Credentials**: Generate temporary random passwords during ISO creation, store only SHA-512 hashes in kickstart, and enforce mandatory password changes on initial GDM login via `chage -d 0`.
- **Component-Derived Group Membership**: Aggregate supplementary user groups from selected components (e.g., `libvirt` from `containers-virt`, `render` and `video` from `intel-oneapi`) combined with administrative `wheel` access.
- **Strict Artifact Protection**: Enforce filesystem permissions of `0600` on generated blueprints, build scripts, ISOs, and credential logs, preventing secret exposure.

### Phase 4: Intent Specification & Single Build Engine *(implemented)*
- **Formal Schema Enforcement**: Define `schema/intent.schema.json` to validate distro, hardware components, hardening profile, disk sizing, and identity.
- **Universal Build Playbook**: Replace disparate per-variant build playbooks with `playbooks/build.yml` executing `role: osbuild` against profile configurations.
- **Example Catalog Migration**: Transition existing variant configurations into committed example intents in `profiles/examples/`.

### Phase 5: Pluggable Remote Logging & Advanced Protections
- **Turnkey Remote Log Shipping** *(implemented)*: Provide a simple `remote_logging.enabled` toggle to ship systemd and audit journals to a remote collector over mTLS via `systemd-journal-upload`.
- **AI Credential & Secret Segmentation** *(Future Goal)*: Apply PCI-inspired separation patterns to LLM provider API keys and agent execution contexts.
- **Self-Service CLI & Web UI** *(Future Goal)*: Introduce an interactive CLI wizard and lightweight web interface wrapping the intent generator.

### Acceptance: 48-hour burn-in on the test laptop

The last acceptance step cannot run in CI: install the CIS example (or your own hardened intent) on the physical test laptop, use it normally for 48 hours, then check that the audit volume stayed at or under its rotation cap and the machine never halted or went single-user:

```bash
sudo du -sh /var/log/audit                       # at or under 512 MB (CIS, PCI-DSS) / 2 GiB (HIPAA)
df -h /var/log/audit
sudo ls -l /var/log/audit                        # audit.log + at most num_logs - 1 rotated files
journalctl -b -0 --since -48h -t syncopated-audit
last -x shutdown reboot runlevel | head          # no unexpected halts or runlevel 1
uptime
sudo syncopated-scan                             # tailored report: deviations "not selected"
```

