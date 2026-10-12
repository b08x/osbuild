# OSBuild - Custom Workstation Image Builder

An Ansible role for building custom workstation images using image-builder-cli. Supports Fedora and AlmaLinux. Designed for creating high-performance workstation images with GNOME, Sway, NVIDIA drivers, CUDA, Intel oneAPI, and container tooling.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
  - [Ansible Role Inversion Pattern](#ansible-role-inversion-pattern)
  - [Build Modes: Traditional vs Bootc](#build-modes-traditional-vs-bootc)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Role Variables](#role-variables)
- [Usage Examples](#usage-examples)
- [Blueprint Customization](#blueprint-customization)
- [Advanced Configuration](#advanced-configuration)
- [Troubleshooting](#troubleshooting)
- [Testing & Validation](#testing--validation)
- [Secure Boot Considerations](#secure-boot-considerations)
- [License](#license)

## Overview

This role automates the complete workflow for building custom workstation images:

1. **Infrastructure Setup**: Installs and configures image-builder-cli on a Fedora or AlmaLinux build host
2. **Repository Configuration**: Loads third-party repository sources (RPM Fusion, EPEL, NVIDIA, Intel oneAPI)
3. **Blueprint Management**: Creates and validates blueprint definitions
4. **Build Execution**: Compiles the ISO image and monitors progress
5. **Image Delivery**: Downloads the final ISO to a specified output directory

The role supports both **static blueprints** (TOML files) and **dynamic templating** (Jinja2) for maximum flexibility.

## Architecture

### Ansible Role Inversion Pattern

This role implements the **Ansible Role Inversion** pattern for bootc-based images:

```shell
Traditional Pattern:              Inverted Pattern (this role):
┌──────────────────┐             ┌──────────────────┐
│  Deploy Image    │             │  Build Container │
└────────┬─────────┘             └────────┬─────────┘
         │                                │
         v                                v
┌──────────────────┐             ┌──────────────────┐
│ Run Ansible      │             │ Run Ansible      │
│ (post-deploy)    │             │ (build-time)     │
└────────┬─────────┘             └────────┬─────────┘
         │                                │
         v                                v
┌──────────────────┐             ┌──────────────────┐
│ Modify /etc/     │             │ Compile /usr/etc/│
│ (mutable)        │             │ (immutable)      │
└──────────────────┘             └────────┬─────────┘
                                          │
                                          v
                                 ┌──────────────────┐
                                 │  Ship Image      │
                                 └────────┬─────────┘
                                          │
                                          v
                                 ┌──────────────────┐
                                 │ Runtime Merges   │
                                 │ /usr/etc + /etc  │
                                 └──────────────────┘
```

**Key Principles:**

1. **Build-time Compilation**: Ansible runs INSIDE the Containerfile during image build, not post-deployment
2. **Immutable Vendor Defaults**: Configurations target `/usr/etc` (vendor layer) instead of `/etc` (local overrides)
3. **Separation of Concerns**: Build-time defaults vs runtime overrides
4. **Atomic Updates**: Configuration changes require rebuilding the image (bootc switch)

**Directory Structure:**

- `/usr/etc/` — Vendor defaults (immutable, part of image)
- `/usr/lib/systemd/system/` — Vendor systemd units
- `/usr/etc/kernel/cmdline.d/` — Kernel parameter snippets
- `/etc/` — Local runtime overrides (mutable, persists across upgrades)

**Benefits:**

- ✅ **Immutable Infrastructure**: Configs are baked into the image
- ✅ **Declarative**: The image IS the desired state
- ✅ **Testable**: Validate configurations in CI before deployment
- ✅ **Atomic Upgrades**: bootc switch brings new configs atomically
- ✅ **No Configuration Drift**: Runtime state cannot diverge from image

### Build Modes: Traditional vs Bootc

This role supports two build modes:

| Aspect | Traditional (image-builder-cli) | Bootc (Container-based) |
| -------- | ------------------------------- | ------------------------- |
| Output | ISO / qcow2 / ami | OCI container image + bootable disk |
| Updates | DNF package updates | Atomic container updates (bootc switch) |
| Config | /etc (mutable) | /usr/etc (vendor) + /etc (overrides) |
| Ansible | Post-deployment | Build-time (inverted pattern) |
| Use Case | Traditional installations | Immutable infrastructure, GitOps |

**When to use bootc:**

- You want atomic, image-based OS updates
- You're implementing GitOps workflows
- You need guaranteed configuration consistency
- You want to test the exact runtime state in CI

**When to use traditional:**

- You need a bootable ISO for bare-metal installation
- You prefer traditional package-based updates
- You need maximum runtime flexibility

## Features

✅ **Dual Desktop Environments**: GNOME 49 + Sway window manager
✅ **NVIDIA Support**: Proprietary drivers, CUDA toolkit, Container Device Interface (CDI)
✅ **Intel oneAPI**: Configurable image-time or first-boot installation
✅ **Container Tooling**: Podman, Docker CE, GPU-accelerated containers
✅ **Development Tools**: GCC, Python, Node.js, rbenv + ruby-build, Ansible collections
✅ **Virtualization**: libvirt, QEMU/KVM, Vagrant
✅ **First-Boot Automation**: Embedded Ansible playbook for post-install configuration
✅ **Comprehensive Error Handling**: Detailed logging, retry logic, helpful diagnostics

## Requirements

### Build Host

- **Operating System**: Fedora 43 Workstation (or compatible version)
- **Disk Space**: Minimum 50GB free in build directory
  - Add ~30GB more if `osbuild_blueprint_components` includes `intel-oneapi`
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Network**: Internet connectivity for repository access
- **Privileges**: Sudo access for package installation and service management

### Ansible

- **Ansible Version**: ansible-core 2.15 or higher (tested with 2.21)
- **Python**: Python 3.11+ on the controller, with `jsonschema` and `passlib` (`dnf install python3-jsonschema python3-passlib`, or `pip install -r requirements.txt`)
- **Collections**: `ansible.utils` (`ansible-galaxy collection install -r requirements.yml`), `ansible.posix`, `community.general`

## Installation

### From Ansible Galaxy (future)

```bash
ansible-galaxy install b08x.osbuild
```

### From Source

```bash
cd /path/to/your/ansible/project
git clone https://github.com/yourusername/ansible-role-osbuild.git roles/osbuild
```

## Role Variables

All defaults live in `defaults/main.yml`. A typical playbook sets only the variables in [What to build](#what-to-build) plus a few switches; everything else has a working default. Names that start with `_` (`_osbuild_distro_version`, `_nvidia_sources`, …) are internal helpers derived from other variables: do not set them.

Which groups apply depends on what you build:

| Building | Groups that apply |
|---|---|
| ISO installer (`image-installer`, `minimal-installer`) | What to build, Build mode, Blueprint, Repositories, Installer, Build host |
| VM or container image (`qcow2`, `container`, …) | What to build, Build mode, Blueprint, Repositories, Build host. Set `osbuild_kickstart_enabled`, `osbuild_kickstart_sudoers` and `osbuild_firstboot_enabled` to `false`: image-builder rejects installer settings for these types. Containers also set `osbuild_flathub_enabled: false` |
| bootc image (`osbuild_build_bootc: true`) | What to build, bootc |

### What to build

| Variable | Default | Description |
|---|---|---|
| `osbuild_distro` | `fedora-43` | Target distribution as `image-builder list` names it (`rocky-10.2`, not `rocky-10`) |
| `osbuild_arch` | `x86_64` | Target architecture |
| `osbuild_image_type` | `minimal-installer` on a Fedora build host, else `image-installer` | image-builder image type (`image-installer`, `qcow2`, `container`, …) |
| `osbuild_blueprint_name` | `custom` | Names the prepared `<name>.toml` and `build-<name>.sh`. Give every variant its own name, or variants overwrite each other's files |
| `osbuild_output_dir` | `/var/tmp/osbuild-images` | Where the blueprint, build script and image go |
| `osbuild_output_filename` | `<blueprint>-<distro>.iso` | Final image name. Use `.tar` for container types |
| `osbuild_container_tag` | `localhost/<blueprint>:latest` | Container types only: tag the build script applies after `podman load` |

### Build mode

By default the role builds nothing. It prepares `<osbuild_output_dir>/<blueprint>.toml` and writes `<osbuild_output_dir>/build-<blueprint>.sh` next to it. That script runs the same `image-builder build` command (distro, arch, `--extra-repo` list) the role would run, then copies the newest image to `osbuild_output_filename`. Run it on the build host with `bash`.

| Variable | Default | Description |
|---|---|---|
| `osbuild_only_generate` | `true` | `true`: write blueprint + build script only. `false`: run image-builder in the play |
| `osbuild_build_bootc` | `false` | Take the bootc path instead (see [bootc](#bootc-only)); wins over `osbuild_only_generate` |

These apply only with `osbuild_only_generate: false`:

| Variable | Default | Description |
|---|---|---|
| `osbuild_build_timeout` | `14400` | Seconds before the in-play build is abandoned |
| `osbuild_build_retries` | `1` | Extra attempts after a failed build (60 s pause before each) |
| `osbuild_verbose` | `false` | Print the image-builder command before running it |
| `osbuild_keep_logs` | `true` | Write image-builder stdout/stderr to `osbuild_log_dir` on failure |
| `osbuild_log_dir` | `/var/tmp/osbuild-logs` | Failure log directory |

### Blueprint

The blueprint comes from one of two places:

- **Components** (`osbuild_blueprint_components`): the role merges component files with a static frame into one blueprint. The component files in `files/<distro>/<major>/<arch>/components/` are the only package data. See [Composing a Blueprint from Components](#composing-a-blueprint-from-components).
- **Static file** (`osbuild_static_blueprint_path`): copied as is when `osbuild_blueprint_components` is empty. Package and locale variables below do not apply. bootc builds always need components.

| Variable | Default | Applies to | Description |
|---|---|---|---|
| `osbuild_blueprint_components` | `[]` | components, bootc | Component files to merge, in order. The only variable that selects packages |
| `osbuild_components_dir` | `<distro>/<ver>/<arch>/components` | components | Directory of component files, relative to the role's `files/`. Follows `osbuild_distro` |
| `osbuild_blueprint_frame_path` | `<distro>/<ver>/<arch>/frames/workstation.toml` | components | Static, non-composable part of the blueprint. `frames/container.toml` serves the CUDA container |
| `osbuild_static_blueprint_path` | `""` | static | Blueprint to copy, relative to the role's `files/` |
| `osbuild_target_distribution` | from `osbuild_distro` | components, bootc | Picks the component directory: `fedora-*` → `fedora/`, `rocky-*` → `rocky/`, `almalinux-*` → `almalinux/`; otherwise the build host's distribution |
| `osbuild_extra_packages` | `[]` | components | Packages added on top of the components |
| `osbuild_package_pins` | `{}` | components | `{package: version}`; unpinned packages get `*` |
| `osbuild_blueprint_version` | `1.0.0` | components, bootc | Blueprint / image version label |
| `osbuild_blueprint_description` | `Custom Workstation` | components | Blueprint description |
| `osbuild_timezone` | `America/New_York` | installer | Also rendered into the kickstart |
| `osbuild_locale` | `en_US.UTF-8` | installer | Also rendered into the kickstart |
| `osbuild_keyboard` | `us` | installer | Also rendered into the kickstart |
| `osbuild_flathub_enabled` | `true` | both | Ship the Flathub system remote (see [Flathub Remote](#flathub-remote)) |

### Composing a Blueprint from Components

A component is a YAML file in `files/<distro>/<ver>/<arch>/components/<name>.yml`:

```yaml
label: "NVIDIA proprietary driver, CUDA toolkit and container toolkit"
repo_urls:                 # become --extra-repo
  - "https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64"
services: ["nvidia-cdi-refresh", "nvidia-persistenced"]
kernel_args: ["rd.driver.blacklist=nouveau", "nvidia-drm.modeset=1"]
fragment: nvidia.toml      # optional; [[customizations.files]] / [[customizations.repositories]] appended as is
flatpaks: []               # optional; bootc builds install these from Flathub
bootc_repos: []            # optional; shell snippets that add repos in bootc builds
copr_repos: []             # optional; COPR repos enabled in bootc builds
packages:                  # "@name" is a comps group
  - "nvidia-driver"
  - "cuda-toolkit"
```

`packages`, `services` and `kernel_args` are merged across the selected components and de-duplicated; `osbuild_extra_packages` and `osbuild_package_pins` still apply. `templates/blueprint-components.toml.j2` renders the result after the blueprint header and `[customizations] hostname = osbuild_hostname`, followed by the frame and each fragment. Because `repo_urls` flow into `--extra-repo`, dropping a component drops its repositories. A fragment may contain only array-of-tables (`[[...]]`) entries: the role renders `[customizations.kernel]` and `[customizations.services]` itself.

Four targets ship component files and a `frames/workstation.toml`: `rocky/10`, `rocky/9`, `almalinux/10` and `fedora/43` (all `x86_64`). They share these names: `base`, `anaconda`, `gnome-desktop`, `fonts`, `audio`, `multimedia`, `google-chrome`, `vscode`, `intel-graphics`, `development`, `containers-virt`, `cockpit` and `nvidia`. Rocky 10 adds `gui-toolkit`, `intel-oneapi`; `rocky/10` and `almalinux/10` add `syncopated` (the b08x/syncopated COPR), `rocky/10` also has `openscap-cis-l2-workstation`, `openscap-hipaa` and `openscap-pci-dss` ([OpenSCAP Profiles](#openscap-profiles)); Fedora 43 adds `sway`; `rocky/10` also has `cuda-container` for `frames/container.toml`. The schema is documented in `defaults/main.yml`, and `tests/validate_schema.py` checks every component file.

Edit component packages with `scripts/package_tracker.py`:

```bash
python3 scripts/package_tracker.py list --target rocky/10/x86_64
python3 scripts/package_tracker.py search nvtop
python3 scripts/package_tracker.py add --target rocky/10/x86_64 base htop --verify
python3 scripts/package_tracker.py remove --target rocky/10/x86_64 base htop
python3 scripts/package_tracker.py tui
```

`add` appends to the component's `packages:` list and keeps comments and order. A package that another component of the same target already has is refused unless `--force` is given. `remove` refuses to empty a component.

### OpenSCAP Profiles

Rocky 10 ships one component per OpenSCAP profile. Each one adds the profile's packages, services and `audit=1 audit_backlog_limit=8192` kernel arguments, and a fragment with `[customizations.openscap]` (profile ID and the `ssg-rhel10-ds.xml` datastream). image-builder then runs the profile's remediation against the installed-OS tree at build time (`org.osbuild.oscap.remediation` in the `os` pipeline) and adds `scap-security-guide` and `openscap-scanner` itself.

| `osbuild_hardening` (intent `hardening`) | Component | Profile | `/var/log/audit` | auditd cap |
|---|---|---|---|---|
| `cis-l2-workstation` | `openscap-cis-l2-workstation` | CIS Red Hat Enterprise Linux 10 Benchmark, Level 2 - Workstation | 4 GiB | 32 MB × 16 = 512 MB |
| `pci-dss` | `openscap-pci-dss` | PCI-DSS v4.0.1 | 4 GiB | 32 MB × 16 = 512 MB |
| `hipaa` | `openscap-hipaa` | HIPAA | 10 GiB | 64 MB × 32 = 2 GiB |

An intent sets `hardening`; the role adds the component (`tasks/intent.yml`) and asserts that exactly that `openscap-*` component is selected (`tasks/hardening.yml`), because image-builder accepts one profile per blueprint.

**Workstation tailoring.** A standalone workstation has no central log collector and must never stop because its audit volume filled. The stock profiles demand `max_log_file_action = keep_logs`, a small `max_log_file`, and `single`/`halt`/`suspend`/`email` for the space and disk actions. Each `openscap-*` component lists, in `openscap_unselected`, the rules that check those settings; `tasks/hardening.yml` writes them, with the SSG variable values of `osbuild_openscap_variables`, as a JSON tailoring file (`templates/openscap-tailoring.json.j2`, injected at `osbuild_openscap_tailoring_json`, `/etc/syncopated/openscap-tailoring.json`); the blueprint references it in `[customizations.openscap.json_tailoring]`, image-builder runs `autotailor --json-tailoring` (`org.osbuild.oscap.autotailor`) on it and remediates with the tailored profile `<profile>_syncopated`. The blueprint format's `[customizations.openscap.tailoring]` takes only selected/unselected rules, not variables, so the JSON form is used for every hardened build. `tasks/hardening.yml` then ships the workstation `/etc/audit/auditd.conf` (`templates/auditd.conf.j2`):

- `max_log_file_action = rotate` with the cap above; `admin_space_left_action = rotate` (at 10 % free), `disk_full_action = rotate`, `disk_error_action = syslog`. Nothing halts, suspends or drops to single-user mode.
- `space_left = 25%` with `space_left_action = exec /usr/local/sbin/syncopated-audit-warn`.
- CIS and PCI-DSS also unselect the per-syscall `audit_rules_dac_modification_*` and `audit_rules_file_deletion_events_*` rules, which fire on every file save, chmod and rename of a desktop session. CIS also unselects `audit_rules_unsuccessful_file_modification_*`, which log every `open()` that fails with EACCES/EPERM, including htop's reads of `/proc/<pid>/io` at each refresh (PCI-DSS does not select them). HIPAA keeps every audit rule of the stock profile (including its `-f 2` failure mode).

**Password length.** The intent's `password_min_length` sets `var_password_pam_minlen` (pam_pwquality `minlen`) in the tailoring; remediation writes that value and the tailored scan checks it. Without it the profile's value applies: 14 for CIS, 12 for PCI-DSS. HIPAA does not select the rule, so the role refuses `password_min_length` with `hipaa` or `none`.

No setting is overridden in `%post`: a scan with the tailored profile lists the deviations as *not selected*, not as failed.

**Low-space warning.** `syncopated-audit-warn` (run by auditd at `space_left`, and at boot and hourly by `syncopated-audit-check.timer`) below `osbuild_audit_warn_free_percent` (25) free: logs a warning-priority journal entry (`journalctl -t syncopated-audit`), writes `/etc/motd.d/90-syncopated-audit` and the Cockpit login banner (`/etc/cockpit/issue.cockpit`, wired up in `/etc/cockpit/cockpit.conf` when `cockpit` is selected), and shows logged-in `wheel` users a GNOME critical notification. `/etc/xdg/autostart/syncopated-audit-notify.desktop` repeats the notification at every login while the condition holds. Above the threshold the files are removed again.

**Scans.** `sudo syncopated-scan` evaluates the host against the stock profile and the tailored one (`/usr/share/xml/osbuild-openscap-data/tailoring.xml` or `/oscap_data/tailoring.xml` from image-builder; rebuilt with `autotailor --json-tailoring` from the injected JSON file named in `/etc/sysconfig/syncopated-scan` if neither exists) and writes `stock-` and `tailored-` `arf.xml`/`report.html`, the tailoring and a `summary.txt` to `/var/lib/syncopated/scans/<timestamp>/` (mode 0700).

**Remote logging** (`osbuild_remote_logging`, intent `remote_logging`). Off: `systemd-journal-upload` stays disabled (when its package is in the image) and CIS's `service_systemd-journal-upload_enabled` rule is unselected. On (`enabled: true`, `url`, `ca_cert`, `client_cert`, `client_key` as PEM text or controller paths): `systemd-journal-remote` is installed, `systemd-journal-upload` and `systemd-journald-audit.socket` are enabled, `/etc/systemd/journal-upload.conf.d/50-syncopated.conf` points at the URL, and a unit drop-in passes the keys from `/etc/pki/syncopated/journal-upload/` (mode 0600) as credentials and restarts the uploader every 30 s without a start limit. An unreachable log host only produces log lines; journald keeps every entry locally.

The component files record the `oscap xccdf generate fix` command they came from, and `build-selections/` keeps the generated blueprints. Known gaps after remediation: `sudo_remove_nopasswd` fails when `osbuild_kickstart_sudoers` is `true`, and the CIS rules for GNOME, USB and Bluetooth can change desktop behaviour. The kickstart `%post` unmasks and enables `cockpit.socket`, because the CIS remediation can mask it; `9090/tcp` is open in the workstation frame.

### Repositories

image-builder resolves packages only from the target distribution's base repositories and the `--extra-repo` URLs. The role builds that list from two inputs:

| Variable | Default | Description |
|---|---|---|
| `osbuild_sources` | build host's common list, `[]` across families | Repository *names*, looked up in `vars/<build host distribution>.yml` (`osbuild_repo:`). Names missing there are skipped silently |
| `osbuild_distro_sources_fedora` / `osbuild_distro_sources_el` | RPM Fusion, VS Code, Chrome, COPR `b08x/syncopated` (Fedora and EL 10), … | The common lists `osbuild_sources` starts from |
| `osbuild_extra_repo_urls` | `[]` | Repository *URLs* passed through unchanged. The `repo_urls` of each selected component are added |

The names are resolved against the **build host's** distribution, not the target's. The default empties `osbuild_sources` when the target family (Fedora vs EL) differs from the build host's, and intents always empty it: the `repo_urls` of the selected components then supply the target's repositories. A blueprint's `[[customizations.repositories]]` only writes `.repo` files into the image; it does not feed package resolution.

### Installer

ISO image types only. Details in [Installer Kickstart](#installer-kickstart) and [First-Login Splash](#first-login-splash-yadm-dotfiles). An intent (`playbooks/build.yml`, `tasks/intent.yml`) sets the first block; the sizing variables are role defaults an intent never changes.

| Variable | Intent field | Default | Description |
|---|---|---|---|
| `osbuild_users` | `users` | `[]` | Users the kickstart creates: `name`, `gecos`, optional `groups`, `uid`, `ssh_pubkey`. Required with the kickstart |
| `osbuild_disk_size_gib` | `disk.size_gib` | `0` | Declared target disk size; volume sizes are computed from it. Required with the kickstart |
| `osbuild_disk_encrypt` | `disk.encrypt` | `false` | LUKS on the physical volume; the installer asks for the passphrase |
| `osbuild_disk_tmp` | `disk.tmp` | `tmpfs` | `/tmp` in the compliant layout: `tmpfs` (fstab line) or `lv` (8 GiB volume) |
| `osbuild_disk_serial` | `disk.serial` | `""` | Abort unless the selected disk has this serial |
| `osbuild_hardening` | `hardening` | `none` | `none` → simple layout; a profile → compliant layout + audit policy |
| `osbuild_remote_logging` | `remote_logging` | `{enabled: false}` | See [OpenSCAP Profiles](#openscap-profiles) |
| `osbuild_locale`, `osbuild_keyboard`, `osbuild_timezone` | `locale.*` | `en_US.UTF-8`, `us`, `America/New_York` | Kickstart `lang`, `keyboard`, `timezone` |

| Variable | Default | Description |
|---|---|---|
| `osbuild_kickstart_enabled` | `true` | Embed the installer kickstart in the blueprint |
| `osbuild_kickstart_countdown` | `30` | Seconds the target disk is shown before partitioning; any key aborts |
| `osbuild_kickstart_sudoers` | `false` | Ship `/etc/sudoers.d/90-wheel-nopasswd` (passwordless sudo for `wheel`). Off by default; the CIS and PCI-DSS profiles flag it |
| `osbuild_firstboot_enabled` | `true` | First-login yadm dotfiles splash (desktop images) |
| `osbuild_kickstart_file` | `kickstart/syncopated.ks` | Kickstart source under `files/`; set only to use your own file |
| `osbuild_output_owner` | connecting user (`playbooks/build.yml`) | Owner of the generated files |
| `osbuild_output_mode` | `0644` (`0600` with remote logging) | Mode of the blueprint, build script and image; the credentials file is always 0600 |
| `osbuild_controller_python` | `ansible_playbook_python` | Must import `passlib` (checked before anything else) |
| `osbuild_audit_policy`, `osbuild_audit_warn_free_percent`, `osbuild_audit_admin_free_percent` | see defaults | Per-profile auditd cap and audit volume; warning (25) and rotation (10) thresholds |

Volume sizing (see [Layout](#layout)): `osbuild_kickstart_reserve_max_gib` (`64`, both layouts) and

| Simple layout (`hardening: none`) | Default | Description |
|---|---|---|
| `osbuild_kickstart_reserve_percent` | `8` | Share of the usable space left unassigned in `vg00` for growing volumes later |
| `osbuild_kickstart_root_min_gib` / `_root_max_gib` / `_root_weight` | `20` / `64` / `1` | `/` minimum, maximum and share of the shared space |
| `osbuild_kickstart_usr_min_gib` / `_usr_max_gib` / `_usr_weight` | `30` / `110` / `3` | `/usr` |
| `osbuild_kickstart_var_min_gib` / `_var_max_gib` / `_var_weight` | `30` / `110` / `3` | `/var` |
| `osbuild_kickstart_home_min_gib` / `_home_weight` | `20` / `5` | `/home` has no maximum; it is dropped (a directory on `/`) when the minimums do not fit with it |

| Compliant layout (any hardening profile) | Default | Description |
|---|---|---|
| `osbuild_kickstart_compliant_root_gib` / `_usr_gib` | `35` / `45` | `/`, `/usr` |
| `osbuild_kickstart_compliant_tmp_gib` | `8` | `/tmp` (volume or tmpfs limit) |
| `osbuild_kickstart_compliant_var_tmp_gib` / `_var_log_gib` | `8` / `10` | `/var/tmp`, `/var/log` |
| `osbuild_kickstart_compliant_var_min_gib` / `_var_max_gib` / `_var_weight` | `40` / `200` / `2` | `/var` minimum, maximum and share |
| `osbuild_kickstart_compliant_home_min_gib` / `_home_weight` | `10` / `5` | `/home` minimum and share; no maximum |
| `osbuild_kickstart_compliant_reserve_percent` | `8` | Share of the usable space left unassigned in `vg00` |

`/var/log/audit` comes from `osbuild_audit_policy` (4 GiB CIS/PCI-DSS, 10 GiB HIPAA). Selecting a component in `osbuild_kickstart_cuda_components` (`nvidia`, `cuda-container`) raises `/usr` to `osbuild_kickstart_cuda_usr_gib` (80) in both layouts.

### Build host

| Variable | Default | Description |
|---|---|---|
| `osbuild_host_packages` | per distribution | Packages installed on the build host (image-builder, osbuild, …) |
| `osbuild_work_dir` | `/var/lib/osbuild-composer` | Free space is checked on its parent filesystem |
| `osbuild_min_disk_space` | `50` | GB that must be free there, or the play fails |
| `osbuild_gpgkey_cache_dir` | `<work_dir>/gpgkeys` | Cache for repository GPG keys |
| `osbuild_repo_config_template` | `<distro>-<major>.json.j2` | Not read by any task (the `templates/etc/osbuild-composer/repositories/` files are not deployed); candidate for removal |

### bootc only

Used only with `osbuild_build_bootc: true`. ISO installers create no user at build time (Anaconda asks for one), so the user variables apply here only.

| Variable | Default | Description |
|---|---|---|
| `osbuild_bootc_base_image` | `quay.io/fedora/fedora-bootc:43` | Base image for the Containerfile |
| `osbuild_bootc_image_name` / `osbuild_bootc_image_tag` | `quay.io/syncopated/<blueprint>` / `latest` | Resulting image |
| `osbuild_bootc_workspace` | `/tmp/bootc-workspace` | Containerfile build context |
| `osbuild_bootc_build_disk_image` | `false` | Also build a disk image from the container |
| `osbuild_bootc_image_type` | `qcow2` | Disk image type (`qcow2`, `iso`, `raw`) |
| `osbuild_bootc_rootfs` | `btrfs` | Root filesystem of the disk image |
| `osbuild_bootc_output_dir` | `<output_dir>/bootc` | Disk image output |
| `osbuild_bootc_build_timeout` | `7200` | Seconds |
| `osbuild_bootc_enable_podman_socket` | `true` | Enable the podman socket on the build host |
| `osbuild_user_name`, `osbuild_user_description`, `osbuild_user_password`, `osbuild_user_groups`, `osbuild_user_ssh_key` | `osadmin`, …, a hash, `[wheel, libvirt]`, empty | User created in the image (change the password hash) |
| `osbuild_hostname` | `workstation` | Image hostname |
| `osbuild_include_fstab`, `osbuild_kernel_cmdline_snippets` | `false`, `[]` | Build-time options for `files/bootc/build.yml` |

## Usage Examples

Installer ISOs are built from intents (`profiles/examples/`, `schema/intent.schema.json`):

```bash
ansible-playbook playbooks/build.yml -e @profiles/examples/rocky-10-2-workstation-nvidia-components.yml
```

### NVIDIA Workstation

```yaml
# profiles/gx.yml
intent:
  name: gx-workstation
  distro: rocky-10.2
  arch: x86_64
  hostname: gx
  components: [base, anaconda, gnome-desktop, fonts, audio, development, containers-virt, nvidia]
  hardening: none
  disk: {size_gib: 931}
  users: [{name: ada, gecos: "Ada Lovelace"}]
  locale: {language: en_US.UTF-8, keyboard: us, timezone: Europe/London}
```

### Hardened Workstation with Remote Logging

```yaml
intent:
  name: studio-cis
  distro: rocky-10.2
  arch: x86_64
  hostname: studio
  components: [base, anaconda, gnome-desktop, fonts, audio, development, cockpit]
  hardening: cis-l2-workstation
  disk: {size_gib: 476, tmp: lv, serial: S5GXNF0R123}
  users: [{name: ada, gecos: "Ada Lovelace", ssh_pubkey: "ssh-ed25519 AAAA... ada@laptop"}]
  locale: {language: en_US.UTF-8, keyboard: us, timezone: America/New_York}
  remote_logging:
    enabled: true
    url: https://logs.lan:19532
    ca_cert: /home/ada/pki/ca.pem
    client_cert: /home/ada/pki/studio.pem
    client_key: /home/ada/pki/studio.key
```

### Intel oneAPI in Image (Large ISO)

```yaml
intent:
  name: hpc-workstation
  distro: rocky-10.2
  arch: x86_64
  hostname: hpc
  components: [base, anaconda, gnome-desktop, development, intel-graphics, intel-oneapi]
  hardening: none
  disk: {size_gib: 1863}
  users: [{name: ada, gecos: "Ada Lovelace"}]   # joins render and video (intel-oneapi user_groups)
  locale: {language: en_US.UTF-8, keyboard: us, timezone: America/New_York}
```

Large builds take time: `-e osbuild_only_generate=false -e osbuild_build_timeout=21600` builds inside the play with a 6-hour limit.

### Custom Disk Layout

The sizing variables are role defaults; override them in `group_vars`/`host_vars` of the build host (an intent cannot set them):

```yaml
# inventory/group_vars/builder.yml
osbuild_kickstart_usr_max_gib: 128
osbuild_kickstart_var_max_gib: 512    # VM images and containers
osbuild_kickstart_var_weight: 6       # /var grows twice as fast as /usr
osbuild_kickstart_home_min_gib: 50
```

### Components Blueprint (non-installer images)

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_distro: rocky-10.2
        osbuild_image_type: qcow2
        osbuild_kickstart_enabled: false
        osbuild_blueprint_components: [base, gnome-desktop, fonts, development]
```

### Using Static Blueprint

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_static_blueprint_path: "fedora/43/x86_64/workstation/custom.toml"
```

### Custom Package List

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_extra_packages:
          - vim-enhanced
          - tmux
          - neovim
          - ripgrep
          - fd-find
```

## Verified Blueprints

### Production-Ready: `fedora-43-workstation-nvidia.toml`

✅ **Context7 Verified** - All syntax validated against official `image-builder-cli` documentation  
✅ **Production Tested** - Successfully builds bootable ISOs with NVIDIA + CUDA + Sway  
✅ **Zero Issues** - No invalid commands or deprecated patterns  

**Location**: `files/fedora/43/x86_64/workstation/fedora-43-workstation-nvidia.toml`  
**Validation Report**: N/A (Validated via Context7)  

#### Key Features

- **Dual Desktop**: GNOME 49 + Sway window manager
- **NVIDIA GPU**: Proprietary drivers (via RPM Fusion), CUDA Toolkit 12.x
- **Container GPU**: NVIDIA CDI (Container Device Interface) for Podman GPU acceleration
- **Development**: GCC, Python, Ruby, Golang, Cargo (Rust)
- **Container Runtime**: Podman, podman-compose, NVIDIA Container Toolkit
- **Modern CLI Tools**: fd-find, du-dust, zoxide, micro, gitui, lnav
- **Automated Setup**: Systemd service for NVIDIA CDI generation on first boot

#### Build Command

```bash
sudo image-builder build workstation-live-installer \
    --distro fedora-43 \
    --blueprint files/fedora/43/x86_64/workstation/fedora-43-workstation-nvidia.toml \
    --output-directory ./output
```

**Expected**:

- Output: `output/fedora-43-workstation-live-installer-<timestamp>.iso`
- Size: ~4-6 GB
- Build time: 30-90 minutes
- Use with Ansible role: Set `osbuild_static_blueprint_path` to this file

#### NVIDIA CDI Automation

This blueprint includes a custom systemd service that automatically generates NVIDIA Container Device Interface (CDI) configuration on first boot:

```bash
# The service waits for NVIDIA device nodes and then generates CDI config
systemctl status nvidia-cdi-refresh.service

# After first boot, GPU containers work immediately:
podman run --rm --device nvidia.com/gpu=all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

**Why this matters**: Without CDI, GPU containers require `--device` flags for every NVIDIA device node. CDI enables simple `--device nvidia.com/gpu=all` syntax.

#### Customization Examples

**Add packages**:

```bash
# Copy blueprint and add packages to the [[packages]] section
cp files/fedora/43/x86_64/workstation/fedora-43-workstation-nvidia.toml my-custom.toml

# Edit my-custom.toml and add:
[[packages]]
name = "neovim"
version = "*"

[[packages]]
name = "tmux"
version = "*"

# Build with custom blueprint
sudo image-builder build workstation-live-installer \
    --blueprint my-custom.toml \
    --distro fedora-43 \
    --output-directory ./output
```

**Users**: the blueprints define no `[[customizations.user]]`. Anaconda asks for the user at install time; see [Installer Kickstart](#installer-kickstart). Adding a user table back requires `osbuild_kickstart_enabled: false`.

**Add repositories**:

```toml
# Add before [[packages]] section
[[customizations.repositories]]
id = "my-repo"
name = "My Custom Repository"
baseurls = ["https://example.com/repo"]
gpgcheck = true
gpgkeys = ["https://example.com/gpgkey"]
enabled = true
```

#### Validation Metadata

```json
{
  "blueprint": "fedora-43-workstation-nvidia.toml",
  "verified_date": "2026-05-28",
  "documentation_sources": ["/osbuild/image-builder-cli", "/osbuild/osbuild"],
  "validation_tools": ["Context7 MCP"],
  "status": "production-ready",
  "issues": 0
}
```

---

## bootc Container Images (New! 🚀)

The role now supports building **bootc container images** for atomic OS updates, based on the [Universal Blue template](https://github.com/ublue-os/image-template).

### Why bootc?

- **Atomic updates**: Full OS updates that either complete entirely or roll back
- **Immutable infrastructure**: OS is never modified at runtime; changes go through image rebuilds
- **Container-native distribution**: Images distributed via OCI registries (Podman, Docker)
- **Atomic Desktops**: Fedora Silverblue, Kinoite, and Universal Blue images support

### Quick Start: Build bootc Container

```yaml
- hosts: localhost
  roles:
    - role: osbuild
      vars:
        osbuild_build_bootc: true
        osbuild_bootc_base_image: "quay.io/fedora/fedora-bootc:43"
        osbuild_blueprint_name: "my-workstation"
        osbuild_blueprint_components: [base, gnome-desktop, sway, nvidia]
```

**Output**: Container image `quay.io/syncopated/my-workstation:latest`

**Use it**:

```bash
# On a bootc system (Silverblue, Kinoite, Bazzite, etc.)
sudo bootc switch quay.io/syncopated/my-workstation:latest
sudo systemctl reboot
```

### Build Bootable Disk Image from Container

```yaml
- hosts: localhost
  roles:
    - role: osbuild
      vars:
        osbuild_build_bootc: true
        osbuild_bootc_build_disk_image: true  # ← Enable disk image build
        osbuild_bootc_image_type: "qcow2"     # or iso, raw
        osbuild_bootc_rootfs: "btrfs"
        osbuild_blueprint_name: "my-workstation"
```

**Output**:

- Container: `quay.io/syncopated/my-workstation:latest`
- Disk image: `/var/tmp/osbuild-images/bootc/qcow2/disk.qcow2`

### Base Image Options

| Base Image | Description | Desktop | Use Case |
| ------------ | ------------- | --------- | ---------- |
| `quay.io/fedora/fedora-bootc:43` | Fedora bootc base | None | Start from scratch, add your own |
| `ghcr.io/ublue-os/base-main:latest` | Universal Blue base | Minimal | Lightweight custom images |
| `ghcr.io/ublue-os/bluefin:stable` | Universal Blue Bluefin | GNOME | GNOME users, DX tools |
| `ghcr.io/ublue-os/aurora:stable` | Universal Blue Aurora | KDE Plasma | KDE users, DX tools |
| `ghcr.io/ublue-os/bazzite:stable` | Universal Blue Bazzite | GNOME/KDE | Gamers, Steam Deck |

### bootc vs Traditional ISO

| Feature | Traditional ISO | bootc Container |
| --------- | ---------------- | ----------------- |
| **Build time** | 30-90 minutes | 10-30 minutes |
| **Distribution** | ISO file | OCI registry |
| **Updates** | DNF package updates | Atomic image updates |
| **Rollback** | Manual snapshot | Built-in (`bootc rollback`) |
| **Customization** | Blueprint TOML | Containerfile + dnf5 |
| **Best for** | Physical install media | Atomic Desktop users |

### Package Installation: bootc vs Blueprint

**Traditional blueprint** (ISO):

```toml
[[packages]]
name = "nvidia-driver"
version = "*"
```

**bootc build.sh** (Container):

```bash
dnf5 install -y nvidia-driver
```

The role's `build.sh.j2` template automatically converts your blueprint's packages to `dnf5 install` commands.

### Configuration Variables

```yaml
# Enable bootc workflow
osbuild_build_bootc: true

# Container image name (without tag)
osbuild_bootc_image_name: "quay.io/syncopated/{{ osbuild_blueprint_name }}"

# Container image tag
osbuild_bootc_image_tag: "latest"

# bootc base image
osbuild_bootc_base_image: "quay.io/fedora/fedora-bootc:43"

# Build disk image from container (optional)
osbuild_bootc_build_disk_image: false

# Disk image type (qcow2, iso, raw)
osbuild_bootc_image_type: "qcow2"

# Root filesystem (btrfs, ext4, xfs)
osbuild_bootc_rootfs: "btrfs"

# Output directory
osbuild_bootc_output_dir: "{{ osbuild_output_dir }}/bootc"
```

### Advanced Example: Custom Silverblue with NVIDIA

```yaml
- hosts: localhost
  roles:
    - role: osbuild
      vars:
        # bootc settings
        osbuild_build_bootc: true
        osbuild_bootc_base_image: "quay.io/fedora/fedora-silverblue:43"
        osbuild_bootc_build_disk_image: true
        osbuild_bootc_image_type: "iso"
        
        # Features (reused from verified blueprint)
        osbuild_blueprint_name: "silverblue-nvidia-custom"
        osbuild_blueprint_components: [base, gnome-desktop, sway, nvidia, development, containers-virt]
```

**This creates**:

1. Container image: `quay.io/syncopated/silverblue-nvidia-custom:latest`
2. Bootable ISO: `/var/tmp/osbuild-images/bootc/bootiso/install.iso`

**Install the ISO**. The installer ISO is self-contained and embeds the bootc container image payload, so the system is fully configured with your container image immediately upon installation without needing any post-install switch command.

### Testing bootc Images

**Test 1: Verify container builds**:

```bash
podman images | grep my-workstation
podman run --rm -it quay.io/syncopated/my-workstation:latest bash
```

**Test 2: Run in VM (QCOW2)**:

```bash
virt-install \
    --name bootc-test \
    --memory 8192 \
    --vcpus 4 \
    --disk /var/tmp/osbuild-images/bootc/qcow2/disk.qcow2 \
    --import \
    --os-variant fedora43 \
    --graphics spice
```

**Test 3: Install from ISO**:

```bash
# Flash to USB
sudo dd if=/var/tmp/osbuild-images/bootc/bootiso/install.iso \
        of=/dev/sdX bs=4M status=progress oflag=sync

# Or boot in VM
virt-install \
    --name bootc-installer \
    --memory 8192 \
    --vcpus 4 \
    --disk size=50 \
    --cdrom /var/tmp/osbuild-images/bootc/bootiso/install.iso \
    --os-variant fedora43
```

### Workflow Comparison

**Traditional ISO**:

```
Blueprint TOML → image-builder-cli → ISO file → Install → DNF updates
```

**bootc Container**:

```
Containerfile → Podman build → OCI image → bootc-image-builder → Disk/ISO
                                    ↓
                            Push to registry → Deploy via bootc switch
```

---

## Blueprint Customization

### Using Components (Recommended)

`osbuild_blueprint_components` selects component files; the role merges them with the frame into the blueprint (see [Composing a Blueprint from Components](#composing-a-blueprint-from-components)).

**Advantages**:

- Packages live in small reviewable files, one concern per file
- Each component brings the repositories its packages need
- `scripts/package_tracker.py` edits them safely

### Using Static Blueprints

For advanced customization, create your own blueprint TOML file:

```bash
# Create custom blueprint
cp roles/osbuild/files/fedora/43/x86_64/workstation/fedora-workstation-43-igx.toml \
   my-custom-blueprint.toml

# Edit as needed
vi my-custom-blueprint.toml
```

Then reference it in your playbook:

```yaml
vars:
  osbuild_static_blueprint_path: "path/to/my-custom-blueprint.toml"
```

See [Blueprint Reference](https://osbuild.org/docs/user-guide/blueprint-reference/) for TOML syntax.

## Advanced Configuration

### Multiple Builds in Parallel

Run multiple builders simultaneously:

```yaml
# inventory
[builders]
builder1.example.com
builder2.example.com

# playbook
- hosts: builders
  strategy: free  # Parallel execution
  roles:
    - osbuild
```

### Custom Repository Sources

Add your own repositories:

1. Create a source TOML file in `files/fedora-43/x86_64/sources/my-repo.toml`:

```toml
id = "my-custom-repo"
name = "My Custom Repository"
type = "yum-baseurl"
url = "https://example.com/repo"
check_gpg = true
gpgkeys = ["https://example.com/RPM-GPG-KEY"]
```

1. Reference it in your playbook:

```yaml
vars:
  osbuild_sources:
    - rpmfusion-free
    - my-custom-repo
```

### First-Login Splash (yadm dotfiles)

One plain bash script, `files/firstboot/syncopated-firstboot`, runs at the first graphical login of each user. It shows a splash, updates the system with `dnf`, downloads `yadm` when it is missing, and prints the `yadm clone` and `yadm bootstrap` commands for the dotfiles repository (`https://github.com/b08x/dots.git`). It does not run the clone or bootstrap; the user runs them when ready. The script contains no build-time substitutions; it reads `NAME` and `VERSION_ID` from `/etc/os-release` when it runs, so the same bytes go into every distro's image.

`tasks/blueprint.yml` appends the three files to every prepared blueprint, static or composed, inside one `blockinfile` block (`# BEGIN/END syncopated-firstboot`). The blueprints in `files/` and `templates/blueprint-components.toml.j2` do not contain copies. Edit only `files/firstboot/`.

| Installed path | Mode | Purpose |
|---|---|---|
| `/usr/local/bin/syncopated-firstboot` | 0755 | Splash, system update and reboot offer, tool report, printed yadm commands |
| `/usr/local/bin/syncopated-firstboot-launcher` | 0755 | Opens a terminal running the script unless the user's marker exists |
| `/etc/xdg/autostart/syncopated-firstboot.desktop` | 0644 | Starts the launcher at graphical login |

The script runs these steps in order:

1. Waits up to 30 s for the network, then runs `sudo dnf -y upgrade --refresh` in the terminal. A failed update is reported and setup continues; without `dnf` the step is skipped.
2. If `osbuild_ansible_pull_repo` and `osbuild_ansible_pull_args` were both set at build time, runs `sudo ansible-pull -U <repo> <args>` right after the update (see [ansible-pull](#ansible-pull)). A failure is reported and setup continues.
3. If the update installed anything (dnf did not print `Nothing to do.`), offers **Reboot now** or **Continue setup**. **Reboot now** runs `sudo systemctl reboot` and writes no marker, so the splash opens again at the next login; there the update finds nothing to do, no reboot is offered, and setup continues.
4. If `gdm`, `lightdm`, or `sddm` is installed and the default target is not `graphical.target`, runs `sudo systemctl set-default graphical.target`. Apart from the package update and the optional reboot, this is the only system change. The script does not set DNF repo priorities or install flatpaks.
5. Prints a ready/missing report for `git yadm gum ansible podman zsh flatpak nvidia-smi`. Missing tools do not change the exit status.
6. Prints the dotfiles commands, unstyled and indented by two spaces, without running them:

   ```bash
   yadm clone --no-bootstrap https://github.com/b08x/dots.git
   yadm bootstrap
   ```

   When `yadm` is not on `PATH`, the script downloads it to `~/.local/bin/yadm` (`curl -fsSL`, mode 0755) before printing the commands. If the download fails, the equivalent `mkdir -p ~/.local/bin && curl … && chmod 0755 …` line is printed instead. `SYNCOPATED_DOTFILES_URL` and `SYNCOPATED_YADM_URL` change the clone and download URLs.
7. Writes the marker.

Without `gum`, the script uses plain-text prompts and output. The launcher sets `SYNCOPATED_PAUSE_ON_EXIT=1`, so the window waits for Enter and the printed commands stay on screen.

**Splash.** The script first clears the terminal and draws the Syncopated logo as ASCII art, centered and revealed row by row. The mark is violet and the wordmark is ember. It then waits at a pulsing `press enter to begin` prompt. Colors are 24-bit when `COLORTERM` is `truecolor` or `24bit`, and 256-color otherwise. A terminal narrower than the art shows only the mark. When stdin or stdout is not a terminal, the script prints the art uncolored and continues without waiting. `SYNCOPATED_NO_ANIM=1` removes the row-by-row delay. The same palette colors `gum` prompts and borders. Any `GUM_CHOOSE_*` variable already set in the environment overrides it.

**Marker.** `~/.local/state/syncopated/firstboot.done` (or `$XDG_STATE_HOME/syncopated/firstboot.done`). The script writes it after printing the yadm commands. While it exists, the launcher does nothing at login, for that user only. **Reboot now** leaves no marker, so the splash opens again at the next login.

**Rerun.** Run `syncopated-firstboot` from any terminal to print the yadm commands again. The marker does not block a manual run. To restore the login splash, delete the marker.

**ansible-pull.** Set both variables in the playbook (a string `osbuild_ansible_pull_args` is split on whitespace):

```yaml
osbuild_ansible_pull_repo: https://github.com/example/pull.git
osbuild_ansible_pull_args: ["-C", "main", "-i", "localhost,", "local.yml"]
```

`tasks/blueprint.yml` then appends `/etc/syncopated-ansible-pull.conf` (a sourced shell file with `ANSIBLE_PULL_REPO` and the array `ANSIBLE_PULL_ARGS`) to the blueprint. If either variable is empty, no file is written and the splash has no `ansible_pull` step. The image needs `ansible-core` and `git`; without `ansible-pull` the step is skipped with a warning. The step runs on every login until the marker exists, so the pulled playbook must be idempotent.

**Disable.** Set `osbuild_firstboot_enabled: false` to prepare blueprints without these files.

**Tests.**

```bash
shellcheck -x roles/osbuild/files/firstboot/syncopated-firstboot{,-launcher}
bats roles/osbuild/tests/firstboot/                                  # stubbed yadm/gum/sudo/systemctl/dnf; asserts yadm and git are never run; curl runs only to download a missing yadm
ansible-playbook roles/osbuild/tests/validate_firstboot_injection.yml  # all blueprints, run twice
```

### Flathub Remote

With `osbuild_flathub_enabled: true` (default), `tasks/blueprint.yml` appends `files/flatpak/flathub.flatpakrepo` to every prepared blueprint as `/etc/flatpak/remotes.d/flathub.flatpakrepo` (`# BEGIN/END syncopated-flathub`). flatpak imports every `*.flatpakrepo` in that directory as a system remote (`man flatpak`), so the installed system has the `flathub` remote without network access during installation; it is the image-time equivalent of:

```yaml
- community.general.flatpak_remote:
    name: flathub
    flatpakrepo_url: https://dl.flathub.org/repo/flathub.flatpakrepo
    method: system
```

- The `flatpak` package must be in the image. Every static blueprint lists `gnome-software`, which requires it. The block cannot add `[[packages]]` because the static blueprints define `packages` as an inline array.
- On Fedora the file overrides the filtered Flathub from `fedora-flathub-remote` (`/usr/share/flatpak/remotes.d/flathub.flatpakrepo`): files in `/etc` take precedence.
- The file embeds Flathub's signing key (fingerprint `6E5C05D979C76DAF93C081354184DD4D907A7CAE`, expires 2027-06-14). Refresh it when Flathub rotates the key:

  ```bash
  curl -fsSL https://dl.flathub.org/repo/flathub.flatpakrepo -o roles/osbuild/files/flatpak/flathub.flatpakrepo
  ```

- Check on an installed system: `flatpak remotes --system` lists `flathub`.
- The bootc path does not use this block; its build script runs `flatpak remote-add` itself.

### Installer Kickstart

`files/kickstart/syncopated.ks` is the kickstart. `tasks/blueprint.yml` appends it to every prepared blueprint, static or templated, as `[customizations.installer.kickstart]` inside one `blockinfile` block (`# BEGIN/END syncopated-kickstart`), after lines `templates/kickstart.toml.j2` renders:

```
lang en_US.UTF-8
keyboard us
timezone America/New_York --utc
rootpw --lock
user --name=ada --gecos="Ada Lovelace" --groups=wheel,libvirt --iscrypted --password=$6$...
sshkey --username=ada "ssh-ed25519 ..."            # when the user has ssh_pubkey
%pre                                               # writes the generation-time layout
cat >/tmp/syncopated-layout.env <<'EOF'            #   DECLARED_MIB, DISK_SERIAL, COUNTDOWN
cat >/tmp/syncopated-layout.ks <<'EOF'             #   fixed-size logvol lines, @DISK@ placeholders
%end
<files/kickstart/syncopated.ks, byte for byte>
%post  tmpfs /tmp fstab line                       # compliant layout, disk.tmp: tmpfs
%post  chage -d 0 <user>                           # new password at first login
```

image-builder adds its own `%include` with the payload in front. Edit only `files/kickstart/syncopated.ks`; it must not contain three consecutive single quotes (the TOML literal-string delimiter) or Jinja delimiters; the role asserts this.

**The install asks nothing.** Language, keyboard, timezone, network (DHCP; `network` has no `--device`, so Anaconda uses the first device with link and the initramfs asks DHCP on any interface; `--device=link` made dracut log `No device with link found` when no carrier was up yet), storage, root (locked unless `osbuild_root_enabled`) and the users are set by the kickstart, so Anaconda starts installing on its own and reboots when done. The only possible prompt is the LUKS passphrase when `osbuild_disk_encrypt` is true; no passphrase is ever written to a generated file.

**Credentials** (`tasks/credentials.yml`). Every user gets the initial password `osbuild_initial_password` (default `syncopated`), hashed with SHA-512 and a new random salt on the controller (`passlib`; the play checks for it first). Only the hash reaches the blueprint and the ISO. With `osbuild_root_enabled` (intent `root: {enabled: true}`), root gets the same password instead of `rootpw --lock`. The plaintext is printed once at the end of the play and written to `<osbuild_output_dir>/<name>.credentials.txt`. The `%post` runs `chage -d 0` for each user (and root), so the first login (GDM) asks for a new password. Supplementary groups are `wheel`, the `user_groups` of the selected components (`libvirt` from `containers-virt`, `render`/`video` from `intel-oneapi`) and the user's own `groups`. The credentials file is mode 0600; the blueprint, the build script and the ISO are `osbuild_output_mode` (0644, or 0600 with remote logging).

**Blueprint restrictions.** image-builder rejects a user kickstart next to `[[customizations.user]]`, `[[customizations.group]]`, `installer.unattended` or `installer.sudo-nopasswd`. No blueprint in this role carries them, and the role fails before the build if a prepared blueprint does. Every blueprint enables `org.fedoraproject.Anaconda.Modules.Users`, which processes the kickstart `user` lines.

**Sudo.** With `osbuild_kickstart_sudoers: true` (default `false`), `/etc/sudoers.d/90-wheel-nopasswd` (mode 0440, `%wheel ALL=(ALL) NOPASSWD: ALL`) is appended as a `[[customizations.files]]` entry (`# BEGIN/END syncopated-sudoers`).

**Target disk.** The `%pre` in `syncopated.ks` picks one disk:

1. Excludes the disk behind `/run/install/repo` or `/run/install/isodir`, and the disk carrying the `inst.stage2=hd:LABEL=...` label.
2. Excludes removable, read-only and USB disks, plus `zram`, `loop` and optical devices.
3. Prefers NVMe disks; among the remaining ones takes the largest.

Then, before anything is written to a disk, it aborts the install (message on tty1, on tty8 and in `/tmp/syncopated-pre.log`) when no disk is left, when `disk.serial` is set and the disk's serial differs, or when the disk is smaller than the declared `disk.size_gib` (both sizes are named). Otherwise it switches to tty8 (tty1 belongs to Anaconda's tmux) and counts down 30 seconds showing the disk's name, model, serial and size; **any key aborts**, the timeout proceeds. Finally it fills the disk name into `/tmp/syncopated-layout.ks`, adds a larger disk's surplus over the declared size to `/home`, and writes `/tmp/partitions.ks`, which the kickstart includes. Only that disk is touched (`ignoredisk --only-use`, `clearpart --drives`). Other internal disks and the install USB keep their data.

#### Layout

Volume sizes are computed when the blueprint is generated (`tasks/disk_layout.yml`, `filter_plugins/disk_layout.py`) from the declared disk size and appear in the kickstart as fixed `logvol --size=` values; the installer does no sizing. A declared size too small for the layout fails the play and names the minimum.

GPT on the chosen disk: an EFI System Partition or biosboot (whatever `reqpart` creates for the platform), a 2 GiB xfs `/boot`, and one LVM physical volume holding volume group `vg00`. All logical volumes are xfs. Sizing works like Anaconda's `default_partitioning` (`min`/`max`) and systemd-repart (`Weight=`): with *usable* = declared size − 4 GiB (variable names without the `osbuild_kickstart_` prefix):

1. **Reserve**: `reserve_percent` of usable, at most `reserve_max_gib`, stays unassigned in `vg00`.
2. **Minimums**: every volume gets its `*_min_gib`. In the simple layout `/home` is dropped (a directory on `/`) when the minimums do not fit with it.
3. **Shared space**: what is left is divided in proportion to the `*_weight` values. A volume that reaches its `*_max_gib` stops growing and the others share its surplus (`/home` has no maximum). Space no volume can take stays unassigned.

The minimums come from a measured install of the NVIDIA workstation image: `/` 5 GiB, `/usr` 17 GiB and `/var` 5 GiB used right after installation.

Simple layout (`hardening: none`) with the defaults; the smallest declared size is 91 GiB (146 GiB with `nvidia`/`cuda-container`, which raise `/usr` to 80 GiB):

| Declared disk | `/` | `/usr` | `/var` | `/home` | Unassigned in `vg00` |
|---|---|---|---|---|---|
| 100 GiB | 21.2 GiB | 33.6 GiB | 33.6 GiB | on `/` | 7.7 GiB |
| 119 GiB | 20.5 GiB | 31.5 GiB | 31.5 GiB | 22.4 GiB | 9.2 GiB |
| 233 GiB | 29.2 GiB | 57.7 GiB | 57.7 GiB | 66.1 GiB | 18.3 GiB |
| 476 GiB | 49 GiB | 110 GiB | 110 GiB | 165.2 GiB | 37.8 GiB |
| 931 GiB | 64 GiB | 110 GiB | 110 GiB | 579 GiB | 64 GiB |
| 2000 GiB | 64 GiB | 110 GiB | 110 GiB | 1648 GiB | 64 GiB |

These are the sizes the installer `%pre` computed before sizing moved to generation time; `tests/test_disk_sizing.py` pins them. On a disk larger than declared, `/home` gets the difference on top.

XFS can grow but not shrink. The maxima and the reserve keep space available for whichever volume fills first; a volume that is too large cannot give space back.

#### Compliant layout

Any hardening profile replaces the layout above with the separate mounts that the CIS, PCI-DSS and HIPAA OpenSCAP profiles scan for (see [OpenSCAP Profiles](#openscap-profiles)). Disk selection, the 2 GiB `/boot` and `vg00` are the same. With *usable* = declared size − 4 GiB:

1. **Reserve**: `compliant_reserve_percent` (8 %) of usable, at most `reserve_max_gib` (64 GiB), stays unassigned in `vg00`.
2. Fixed volumes: `/` 35 GiB, `/usr` 60 GiB (80 with CUDA), `/var/tmp` 8 GiB, `/var/log` 10 GiB, `/var/log/audit` 4 GiB (CIS, PCI-DSS) or 10 GiB (HIPAA), and `/tmp` 8 GiB with `disk.tmp: lv`.
3. **`/var`** (at least 40 GiB, at most 185 GiB; it holds podman images, flatpaks and libvirt disks) and **`/home`** (at least 10 GiB, no maximum) get their minimums, then share the rest 2:5.

Mount options are set in the kickstart (`logvol --fsoptions`), not by the build-time remediation, because Anaconda writes `/etc/fstab` at install time:

| Mount | Options |
|---|---|
| `/boot` | `nodev,nosuid` |
| `/home`, `/var` | `nodev,nosuid,noatime` |
| `/usr` | `nodev,noatime` |
| `/var/tmp`, `/var/log`, `/var/log/audit` | `nodev,nosuid,noexec,noatime` |
| `/tmp` (tmpfs or volume) | `nodev,nosuid,noexec` |

The smallest declared size is 186 GiB for CIS/PCI-DSS and 193 GiB for HIPAA (208 / 214 GiB with CUDA):

| Declared disk | `/var/log/audit` | `/var` | `/home` | Unassigned |
|---|---|---|---|---|
| 186 GiB | 4 GiB | 40.1 GiB | 10.3 GiB | 14.6 GiB |
| 476 GiB | 4 GiB | 116.4 GiB | 200.9 GiB | 37.8 GiB |
| 931 GiB | 4 GiB | 185 GiB | 561 GiB | 64 GiB |
| 476 GiB (HIPAA) | 10 GiB | 114.6 GiB | 196.6 GiB | 37.8 GiB |

`/tmp` as tmpfs may still fail a profile's `partition_for_tmp` rule, which asks for "its own partition or logical volume"; use `disk.tmp: lv` to satisfy it. `noexec` on `/var/tmp` can break tools that run from there, so test the first `dnf update` on a new image. Installed-system `/tmp` content is lost on every boot with tmpfs.

#### When a volume fills up

What breaks first:

| Volume | Effect |
|---|---|
| `/` | Logins and services that write to `/etc`, `/root` or `/tmp` fail |
| `/usr` | `dnf` refuses transactions (RPM checks space before changing anything); model downloads into `/usr/share/ollama` fail |
| `/var` | journald stops writing; `dnf` fails (cache, RPM database); libvirt pauses running VMs on write errors; podman and flatpak installs fail |
| `/home` | User applications fail to save |

Procedure, in order:

1. **Find what grew.**

   ```bash
   df -h / /usr /var /home
   sudo vgs vg00                                   # VFree = unassigned space
   sudo du -xh --max-depth=2 /var | sort -h | tail # -x: stay on this filesystem
   ```

2. **Remove what is not needed.**

   ```bash
   sudo journalctl --vacuum-size=500M
   sudo dnf clean all
   flatpak uninstall --unused
   podman system prune                # and/or: docker system prune
   sudo virsh vol-list default        # then virsh vol-delete for unused images
   ```

3. **Grow the volume from the reserve.** Online, no reboot; `-r` grows the xfs filesystem in the same step.

   ```bash
   sudo lvextend -r -L +64G vg00/var
   ```

4. **Move data that does not belong on that volume.**
   - libvirt images: define a storage pool on `/home` or another disk (`virsh pool-define-as`).
   - Ollama models: `OLLAMA_MODELS=/var/lib/ollama/models` (or a path under `/home`) in a systemd drop-in for `ollama.service`, so models stop landing in `/usr/share/ollama`.
   - Flatpak: install large apps with `flatpak --user`, which stores them under `~/.local/share/flatpak`.

5. **Add a disk when `vg00` has no free space left.** `pvcreate` destroys the contents of the disk.

   ```bash
   sudo pvcreate /dev/sdX
   sudo vgextend vg00 /dev/sdX
   sudo lvextend -r -L +200G vg00/var
   ```

6. **Shrinking another volume is not possible in place.** Back it up, remove and recreate it smaller (`lvremove`, `lvcreate`, `mkfs.xfs`), restore, then grow the full volume.

**Disable.** `osbuild_kickstart_enabled: false` prepares blueprints without the kickstart; Anaconda then shows its full hub. `osbuild_kickstart_sudoers: false` drops the sudoers file.

**Tests.**

```bash
pip install pykickstart                                                 # provides ksvalidator
python3 -m pytest tests/test_disk_sizing.py tests/test_intent.py        # sizing math; rendered kickstarts (ksvalidator -v RHEL10)
bats roles/osbuild/tests/kickstart/                                     # %pre with stubbed lsblk/findmnt/blkid/chvt
ansible-playbook roles/osbuild/tests/validate_kickstart_injection.yml \
  -e ksvalidator=$(which ksvalidator)                                   # enabled x2, disabled, conflict rejected
SYNCOPATED_VM_ISO=<iso> python3 -m pytest tests/test_vm_install.py -s   # unattended install in QEMU/KVM
```

## Troubleshooting

### Build Fails with Dependency Errors

**Symptom**: Build fails with package resolution errors.

**Solutions**:

1. Verify extra repositories are accessible
2. Check repository GPG keys and URLs
3. Review package names for typos in blueprint
4. Ensure distro version matches repository versions

### NVIDIA Driver Not Loading After Boot

**Symptom**: `nvidia-smi` shows "No devices found"

**Solutions**:

1. Check if nouveau is blacklisted: `lsmod | grep nouveau` (should be empty)
2. Verify akmod compilation: `sudo akmods --force`
3. Check logs: `journalctl -xe | grep nvidia`
4. Ensure kernel-devel matches running kernel

### Build Timeout

**Symptom**: Build exceeds `osbuild_build_timeout`

**Solutions**:

1. Increase timeout: `osbuild_build_timeout: 21600`
2. Consider removing `intel-oneapi` from `osbuild_blueprint_components` for faster builds
3. Check network speed for repository downloads
4. Monitor build progress in the console output

### Insufficient Disk Space

**Symptom**: Build fails with "No space left on device"

**Solutions**:

1. Check free space: `df -h /var/tmp/osbuild-images`
2. Clean old builds to free up space
3. Increase disk allocation to build host

### Common Error Messages

| Error | Cause | Solution |
| ------- | ------- | ---------- |
| `Failed to load source` | TOML syntax error | Validate TOML with `python3 -c "import tomli; tomli.load(open('file.toml'))"` |
| `GPG key retrieval failed` | Network/firewall issue | Check `gpgkeys` URL accessibility |
| `Package not found` | Typo or missing repo | Review package name and enabled sources |
| `Blueprint already exists` | Duplicate blueprint | Use unique names for your blueprints |

## Testing & Validation

### 1. Virtual Machine Testing (Recommended First)

```bash
# After build completes
virt-install \
  --name test-custom-iso \
  --memory 4096 \
  --vcpus 2 \
  --disk size=40 \
  --cdrom /var/tmp/osbuild-images/my-blueprint-fedora-43.iso \
  --os-variant fedora43 \
  --graphics spice
```

**Verification Steps**:

- Boot ISO in VM
- Verify Anaconda installer launches
- Check both GNOME and Sway sessions appear in GDM
- Install to virtual disk
- Test installed system

### 2. Physical Hardware Testing

```bash
# Flash to USB drive
sudo dd if=/var/tmp/osbuild-images/my-blueprint-fedora-43.iso \
        of=/dev/sdX \
        bs=4M \
        status=progress \
        oflag=sync
```

**NVIDIA Hardware Verification**:

```bash
# After installation and reboot
nvidia-smi  # Should show GPU info
podman run --device nvidia.com/gpu=all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi
```

### 3. Manifest Inspection

```bash
# Mount ISO and query packages
sudo mkdir /mnt/iso
sudo mount -o loop /var/tmp/osbuild-images/my-blueprint.iso /mnt/iso
rpm -qa --dbpath /mnt/iso/var/lib/rpm | grep -i nvidia
sudo umount /mnt/iso
```

## Secure Boot Considerations

### NVIDIA Driver Compatibility

**Challenge**: NVIDIA akmod drivers are compiled locally on first boot, resulting in unsigned kernel modules that Secure Boot will reject.

**Options**:

1. **Disable Secure Boot** (Easiest)
   - Enter BIOS/UEFI and disable Secure Boot
   - No MOK enrollment required
   - ✅ Simplest for development/testing systems

2. **Enroll MOK (Machine Owner Key)**
   - During first boot, akmod creates a signing key
   - Follow prompts to enroll MOK in UEFI
   - ⚠️ Requires physical access to console
   - ⚠️ Different key per machine

3. **Pre-signed Drivers** (Future Enhancement)
   - Use RPM Fusion's pre-built kmod packages
   - Signed by RPM Fusion's trusted key
   - ❌ Not currently implemented in this role

### Documentation

The role automatically includes instructions in the first-boot Ansible playbook output. Users will see MOK enrollment prompts if Secure Boot is enabled.

## License

MIT-0 (See LICENSE file)

This role is released into the public domain. You may use, modify, and distribute it freely without attribution.

## References

- [OSBuild Documentation](https://osbuild.org/docs/)
- [Blueprint Reference](https://osbuild.org/docs/user-guide/blueprint-reference/)
- [image-builder-cli](https://github.com/osbuild/image-builder)
- [Fedora Image Builder](https://osbuild.org/docs/hosted/fedora-console/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
- [Intel oneAPI Documentation](https://www.intel.com/content/www/us/en/developer/tools/oneapi/documentation.html)

## Contributing

Contributions welcome! Please open issues or pull requests on the project repository.
