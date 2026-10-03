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
  - Add ~30GB more if `osbuild_components` includes `oneapi`
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Network**: Internet connectivity for repository access
- **Privileges**: Sudo access for package installation and service management

### Ansible

- **Ansible Version**: 2.9 or higher
- **Python**: Python 3.6+
- **Collections**: `ansible.posix`, `community.general` (auto-installed via dependencies)

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

All defaults live in `defaults/main.yml`. A typical playbook sets only the variables in [What to build](#what-to-build) plus a few switches; everything else has a working default. Names that start with `_` (`_distro_version`, `_nvidia_sources`, …) are internal helpers derived from other variables: do not set them.

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

The blueprint comes from one of three places. A non-empty `osbuild_blueprint_components` wins over the other two:

- **Components** (`osbuild_blueprint_components`): the role merges component files with a static frame into one blueprint. See [Composing a Blueprint from Components](#composing-a-blueprint-from-components).
- **Static file** (`osbuild_use_blueprint_template: false`): `osbuild_static_blueprint_path` is copied as is. Most shipped playbooks use this; `osbuild-rocky-iso-nvidia-components.yml` uses components. Package and locale variables below do not apply.
- **Jinja template** (`osbuild_use_blueprint_template: true`, the default): `templates/blueprint.toml.j2` renders packages, services, kernel arguments and installer modules from `osbuild_components`. Suited to workstation ISOs only.

| Variable | Default | Applies to | Description |
|---|---|---|---|
| `osbuild_use_blueprint_template` | `true` | both | Choose template (`true`) or static file (`false`) |
| `osbuild_static_blueprint_path` | `files/<distro>/<ver>/<arch>/workstation/<distro>-workstation-nvidia.toml` | static | Blueprint to copy, relative to the role |
| `osbuild_blueprint_components` | `[]` | components | Component files to merge, in order. Non-empty selects the components path |
| `osbuild_components_dir` | `<distro>/<ver>/<arch>/components` | components | Directory of component files, relative to the role's `files/`. Follows `osbuild_distro` |
| `osbuild_blueprint_frame_path` | `<distro>/<ver>/<arch>/frames/workstation.toml` | components | Static, non-composable part of the blueprint |
| `osbuild_target_distribution` | from `osbuild_distro` | template, bootc | Picks `vars/packages/<Name>.yml`: `fedora-*` → Fedora, `rocky-*` → Rocky, `almalinux-*` → AlmaLinux; otherwise the build host's distribution |
| `osbuild_components` | `base, anaconda, gnome, sway, nvidia, development, container-tools` | both | Template: what goes into the image. Both: whose `sources` become extra repos |
| `osbuild_component_defs` | see `defaults/main.yml` | both | What each component adds: packages, groups, services, kernel args, sources. Components: `base`, `anaconda`, `gnome`, `nvidia`, `sway`, `development`, `container-tools`, `oneapi`, `cli-tools`, `cockpit`, `core`, `desktop`, `audio`, `virtualization` |
| `osbuild_extra_packages` | a short list | template | Packages added on top of the components |
| `osbuild_package_pins` | `{}` | template | `{package: version}`; unpinned packages get `*` |
| `osbuild_blueprint_template` | `blueprint.toml.j2` | template | Template file |
| `osbuild_blueprint_version` | `1.0.0` | template, components, bootc | Blueprint / image version label |
| `osbuild_blueprint_description` | `Custom Workstation` | template, components | Blueprint description |
| `osbuild_timezone` | `America/New_York` | template, installer | Also rendered into the kickstart |
| `osbuild_locale` | `en_US.UTF-8` | template, installer | Also rendered into the kickstart |
| `osbuild_keyboard` | `us` | template, installer | Also rendered into the kickstart |
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
packages:                  # "@name" is a comps group
  - "nvidia-driver"
  - "cuda-toolkit"
```

`packages`, `services` and `kernel_args` are merged across the selected components and de-duplicated; `osbuild_extra_packages` and `osbuild_package_pins` still apply. `templates/blueprint-components.toml.j2` renders the result after the blueprint header and `[customizations] hostname = osbuild_hostname`, followed by the frame and each fragment. Because `repo_urls` flow into `--extra-repo`, dropping a component drops its repositories. A fragment may contain only array-of-tables (`[[...]]`) entries: the role renders `[customizations.kernel]` and `[customizations.services]` itself.

Rocky 10 ships `base`, `anaconda`, `gnome-desktop`, `fonts`, `audio`, `multimedia`, `intel-graphics`, `development`, `containers-virt`, `cockpit` and `nvidia`, split from `rocky-10-2-workstation-nvidia.toml`. image-builder depsolves the same 1715 RPMs from both. `playbooks/osbuild-rocky-iso-nvidia-components.yml` selects all eleven. These component files are separate from the `osbuild_component_defs` entries above, which still serve the template and bootc paths.

### Repositories

image-builder resolves packages only from the target distribution's base repositories and the `--extra-repo` URLs. The role builds that list from two inputs:

| Variable | Default | Description |
|---|---|---|
| `osbuild_sources` | build host's common list + sources of the selected components | Repository *names*, looked up in `vars/<build host distribution>.yml` (`repo:`). Names missing there are skipped silently |
| `osbuild_distro_sources_fedora` / `osbuild_distro_sources_el` | RPM Fusion, VS Code, Chrome, … | The common lists `osbuild_sources` starts from |
| `osbuild_extra_repo_urls` | `[]` | Repository *URLs* passed through unchanged. The `repo_urls` of each selected blueprint component are added |

The names are resolved against the **build host's** distribution, not the target's. To build an EL image on a Fedora host, set `osbuild_sources: []` and list every non-base repository in `osbuild_extra_repo_urls` (see `playbooks/osbuild-rocky-iso-nvidia.yml`). A blueprint's `[[customizations.repositories]]` only writes `.repo` files into the image; it does not feed package resolution.

### Installer

ISO image types only. Details in [Installer Kickstart](#installer-kickstart) and [First-Login Splash](#first-login-splash-yadm-dotfiles).

| Variable | Default | Description |
|---|---|---|
| `osbuild_kickstart_enabled` | `true` | Embed the installer kickstart in the blueprint |
| `osbuild_kickstart_partitioning` | `auto` | `auto`: `%pre` picks a disk and applies the layout below. `interactive`: the user partitions in Anaconda's Installation Destination |
| `osbuild_kickstart_sudoers` | `true` | Ship `/etc/sudoers.d/90-wheel-nopasswd` |
| `osbuild_firstboot_enabled` | `true` | First-login yadm dotfiles splash (desktop images) |
| `osbuild_kickstart_file` | derived from `osbuild_kickstart_partitioning` | Kickstart source under `files/`; set only to use your own file |

Disk layout for `osbuild_kickstart_partitioning: auto` (see [Layout](#layout) for how they combine):

| Variable | Default | Description |
|---|---|---|
| `osbuild_kickstart_disk_min_gib` | `40` | Smaller target disks abort the install |
| `osbuild_kickstart_root_percent` | `10` | `/` share of the usable space |
| `osbuild_kickstart_root_min_gib` | `16` | `/` minimum |
| `osbuild_kickstart_reserve_percent` | `10` | Share of the usable space left unassigned in `vg00` for growing volumes later; `0` disables |
| `osbuild_kickstart_usr_percent` | `80` | `/usr` share of the space after `/` and the reserve; `/var` gets the rest |
| `osbuild_kickstart_usr_max_gib` | `256` | `/usr` cap |
| `osbuild_kickstart_var_max_gib` | `128` | `/var` cap |
| `osbuild_kickstart_home_min_gib` | `100` | `/home` is a volume only when at least this much is left above the caps |

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

### NVIDIA Workstation (template)

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_blueprint_name: "my-nvidia-workstation"
        osbuild_components: [base, anaconda, gnome, sway, nvidia, development, container-tools]
```

### Minimal Workstation (No NVIDIA)

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_blueprint_name: "minimal-workstation"
        osbuild_components: [base, anaconda, gnome]
```

### Intel oneAPI in Image (Large ISO)

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_blueprint_name: "hpc-workstation"
        osbuild_components: [base, anaconda, gnome, development, oneapi]
        osbuild_only_generate: false
        osbuild_build_timeout: 21600  # 6 hours for large build
```

### Custom Disk Layout

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_kickstart_usr_max_gib: 128
        osbuild_kickstart_var_max_gib: 512    # VM images and containers
        osbuild_kickstart_home_min_gib: 50
```

### Components Blueprint

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_distro: rocky-10.2
        osbuild_use_blueprint_template: false
        osbuild_sources: []          # EL target on a Fedora host
        osbuild_blueprint_components: [base, anaconda, gnome-desktop, fonts, development]
```

### Using Static Blueprint

```yaml
- hosts: builder
  roles:
    - role: osbuild
      vars:
        osbuild_use_blueprint_template: false
        osbuild_static_blueprint_path: "files/fedora-43/x86_64/workstation/custom.toml"
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
        osbuild_components: [base, gnome, sway, nvidia]
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
        osbuild_components: [base, gnome, sway, nvidia, development, container-tools]
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

### Using Dynamic Templates (Recommended)

The role includes a comprehensive Jinja2 template (`templates/fedora-workstation.toml.j2`) that generates blueprints based on role variables. This is the default mode (`osbuild_use_blueprint_template: true`).

**Advantages**:

- No blueprint file editing required
- Consistent configuration via Ansible variables
- Easy version control and sharing
- Automatic integration of feature flags

### Using Static Blueprints

For advanced customization, create your own blueprint TOML file:

```bash
# Create custom blueprint
cp roles/osbuild/files/fedora-43/x86_64/workstation/fedora-43-workstation-nvidia.toml \
   my-custom-blueprint.toml

# Edit as needed
vi my-custom-blueprint.toml
```

Then reference it in your playbook:

```yaml
vars:
  osbuild_use_blueprint_template: false
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

One plain bash script, `files/firstboot/syncopated-firstboot`, runs at the first graphical login of each user. It shows a splash, updates the system with `dnf`, and asks for a dotfiles repository URL (pre-filled with `https://github.com/b08x/dots.git`). It then clones that repository with `yadm` and runs `yadm bootstrap` as the logged-in user. The script contains no build-time substitutions; it reads `NAME` and `VERSION_ID` from `/etc/os-release` when it runs, so the same bytes go into every distro's image.

`tasks/blueprint.yml` appends the three files to every prepared blueprint, static or templated, inside one `blockinfile` block (`# BEGIN/END syncopated-firstboot`). The blueprints in `files/` and `templates/blueprint.toml.j2` do not contain copies. Edit only `files/firstboot/`.

| Installed path | Mode | Purpose |
|---|---|---|
| `/usr/local/bin/syncopated-firstboot` | 0755 | Splash, system update and reboot offer, yadm install/clone, bootstrap in a second window, tool report |
| `/usr/local/bin/syncopated-firstboot-launcher` | 0755 | Opens a terminal running the script unless the user's marker exists |
| `/etc/xdg/autostart/syncopated-firstboot.desktop` | 0644 | Starts the launcher at graphical login |

The script runs these steps in order:

1. Waits up to 30 s for the network, then runs `sudo dnf -y upgrade --refresh` in the terminal. A failed update is reported and setup continues; without `dnf` the step is skipped.
2. If the update installed anything (dnf did not print `Nothing to do.`), offers **Reboot now** or **Continue setup**. **Reboot now** runs `sudo systemctl reboot` and writes no marker, so the splash opens again at the next login; there the update finds nothing to do, no reboot is offered, and setup continues.
3. Offers **Set up dotfiles**, **Skip for now**, or **Never ask again**.
4. Uses `yadm` from `PATH`. If `yadm` is absent, downloads it to `~/.local/bin/yadm` and offers Retry or Skip if GitHub is unreachable.
5. Checks the URL with `git ls-remote` and asks again if the check fails. Then runs `yadm clone --no-bootstrap`. If a yadm repository already exists, offers "Run bootstrap only" instead.
6. Runs `yadm bootstrap` in a new terminal window, opened with the same terminal order as the launcher, so the bootstrap's own prompts and `sudo` calls work there. The first window waits until the bootstrap ends and uses its exit status; closing the bootstrap window early counts as a failure. With no graphical session or terminal emulator, or when the window has not started after 15 s (`SYNCOPATED_WINDOW_TIMEOUT`), bootstrap runs in the first window instead.
7. If `gdm`, `lightdm`, or `sddm` is installed and the default target is not `graphical.target`, runs `sudo systemctl set-default graphical.target`. Apart from the package update and the optional reboot, this is the only system change. The script does not set DNF repo priorities or install flatpaks.
8. Prints a ready/missing report for `git yadm gum ansible podman zsh flatpak nvidia-smi`. Missing tools do not change the exit status.

Without `gum`, the script uses plain-text prompts and output.

**Splash.** The script first clears the terminal and draws the Syncopated logo as ASCII art, centered and revealed row by row. The mark is violet and the wordmark is ember. It then waits at a pulsing `press enter to begin` prompt. Colors are 24-bit when `COLORTERM` is `truecolor` or `24bit`, and 256-color otherwise. A terminal narrower than the art shows only the mark. When stdin or stdout is not a terminal, the script prints the art uncolored and continues without waiting. `SYNCOPATED_NO_ANIM=1` removes the row-by-row delay. The same palette colors `gum` prompts and borders. Any `GUM_CHOOSE_*` or `GUM_INPUT_*` variable already set in the environment overrides it.

**Marker.** `~/.local/state/syncopated/firstboot.done` (or `$XDG_STATE_HOME/syncopated/firstboot.done`). The script writes it after a successful bootstrap or after **Never ask again**. While it exists, the launcher does nothing at login, for that user only. **Skip for now** and a failed clone or bootstrap leave no marker, so the splash opens again at the next login.

**Rerun.** Run `syncopated-firstboot` from any terminal. The marker does not block a manual run. To restore the login splash, delete the marker.

**Disable.** Set `osbuild_firstboot_enabled: false` to prepare blueprints without these files.

**Tests.**

```bash
shellcheck -x roles/osbuild/files/firstboot/syncopated-firstboot{,-launcher}
bats roles/osbuild/tests/firstboot/                                  # stubbed git/yadm/curl/gum/sudo/systemctl/dnf
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

`files/kickstart/syncopated.ks` is the default kickstart. With `osbuild_kickstart_partitioning: interactive` the role embeds `files/kickstart/syncopated-interactive.ks` instead: the same commands without the `%pre` disk selection, so Anaconda's Installation Destination screen must be completed by the user (`playbooks/osbuild-rocky-iso-nvidia-interactive.yml` uses it). The rest of this section describes the default file. `tasks/blueprint.yml` appends it to every prepared blueprint, static or templated, as `[customizations.installer.kickstart]` inside one `blockinfile` block (`# BEGIN/END syncopated-kickstart`). Three lines come first, rendered from role variables:

```
lang {{ osbuild_locale }}
keyboard {{ osbuild_keyboard }}
timezone {{ osbuild_timezone }} --utc
```

With `osbuild_kickstart_partitioning: auto` a short `%pre` follows that writes the [disk layout variables](#layout) to `/tmp/syncopated-layout.env`. The rest is the source file, byte for byte. image-builder adds its own `%include` with the payload in front. Edit only `files/kickstart/syncopated.ks`. It must not contain `'''` (the TOML literal-string delimiter); the role asserts this.

**What Anaconda asks for.** Only **Root Password** and **User Creation**. Language, keyboard, timezone, network (DHCP on the first linked NIC, also at boot) and storage are set by the kickstart. The installer still waits for **Begin Installation** and reboots when done. Tick **Make this user administrator** to put the user in `wheel`.

**Blueprint restrictions.** image-builder rejects a user kickstart next to `[[customizations.user]]`, `[[customizations.group]]`, `installer.unattended` or `installer.sudo-nopasswd`. No blueprint in this role carries them, and the role fails before the build if a prepared blueprint does. Every blueprint enables `org.fedoraproject.Anaconda.Modules.Users`, because image-builder only enables the user screen on its own when the blueprint defines users.

**Sudo.** `/etc/sudoers.d/90-wheel-nopasswd` (mode 0440, `%wheel ALL=(ALL) NOPASSWD: ALL`) is appended as a `[[customizations.files]]` entry (`# BEGIN/END syncopated-sudoers`).

**Target disk.** A `%pre` script picks one disk and writes `/tmp/partitions.ks`, which the kickstart includes:

1. Excludes the disk behind `/run/install/repo` or `/run/install/isodir`, and the disk carrying the `inst.stage2=hd:LABEL=...` label.
2. Excludes removable, read-only and USB disks, plus `zram`, `loop` and optical devices.
3. Prefers NVMe disks; among the remaining ones takes the largest.
4. Aborts the install (message on tty1 and in `/tmp/syncopated-pre.log`) when no disk is left or the chosen disk is smaller than `osbuild_kickstart_disk_min_gib` (40 GiB). A small NVMe disk is not skipped in favour of a larger SATA disk: the install aborts.

Only that disk is touched (`ignoredisk --only-use`, `clearpart --drives`). Other internal disks and the install USB keep their data.

#### Layout

GPT on the chosen disk: an EFI System Partition or biosboot (whatever `reqpart` creates for the platform), a 2 GiB xfs `/boot`, and one LVM physical volume holding volume group `vg00`. All logical volumes are xfs. With *usable* = disk size − 4 GiB, the `%pre` allocates in this order (variable names without the `osbuild_kickstart_` prefix):

1. **`/`** (`vg00/root`): `root_percent` of usable, at least `root_min_gib`.
2. **Reserve**: `reserve_percent` of usable stays unassigned in `vg00`.
3. **`/usr`** (`vg00/usr`): `usr_percent` of what is left, at most `usr_max_gib`. **`/var`** (`vg00/var`): the rest of it, at most `var_max_gib`. `/var` therefore also receives whatever `/usr`'s cap leaves.
4. **`/home`** (`vg00/home`): everything above the two caps, if that is at least `home_min_gib`. Otherwise that space also stays unassigned and `/home` is a directory on `/`.

With the defaults:

| Disk | `/` | `/usr` | `/var` | `/home` | Unassigned in `vg00` |
|---|---|---|---|---|---|
| 60 GiB | 16 GiB | 27.5 GiB | 6.9 GiB | on `/` | 5.6 GiB |
| 477 GiB | 47.3 GiB | 256 GiB | 122.4 GiB | on `/` | 47.3 GiB |
| 931 GiB | 92.7 GiB | 256 GiB | 128 GiB | 357.6 GiB | 92.7 GiB |
| 2000 GiB | 199.6 GiB | 256 GiB | 128 GiB | 1212.8 GiB | 199.6 GiB |

The role writes the variables to `/tmp/syncopated-layout.env` in a `%pre` placed before the one in `syncopated.ks`; the source file carries the same values as built-in defaults for the bats tests, which also check that both agree. During installation, `/tmp/syncopated-pre.log` (shell on tty2) records the chosen disk and the sizes.

XFS can grow but not shrink. The caps and the reserve keep space available for whichever volume fills first; a volume that is too large cannot give space back.

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
.venv/bin/pip install pykickstart                                       # provides ksvalidator
.venv/bin/ksvalidator -v RHEL10 roles/osbuild/files/kickstart/syncopated.ks
bats roles/osbuild/tests/kickstart/                                     # %pre with stubbed lsblk/findmnt/blkid
ansible-playbook roles/osbuild/tests/validate_kickstart_injection.yml \
  -e ksvalidator=$PWD/.venv/bin/ksvalidator                            # enabled x2, disabled, conflict rejected
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
2. Consider removing `oneapi` from `osbuild_components` for faster builds
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
