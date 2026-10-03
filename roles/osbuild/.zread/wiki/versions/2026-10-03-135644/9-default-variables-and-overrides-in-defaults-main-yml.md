This page explains the **default variables** defined in `defaults/main.yml` and how they can be **overridden** to customize the OSBuild role's behavior. This file serves as the **single source of truth** for configurable parameters, ensuring consistency across builds while allowing flexibility for specific use cases.

The variables are organized into logical sections, each governing a distinct aspect of the build process: **build configuration**, **component selection**, **repository management**, **user customization**, **output settings**, and **advanced bootc integration**. Below, we break down the purpose, structure, and override mechanisms for each section.

---

## 1. Build Configuration
This section defines the **foundational parameters** for the build, including the target distribution, architecture, and build mode.

### Key Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_distro` | `"fedora-43"` | Target distribution and version (e.g., `fedora-43`, `almalinux-10.2`, `rocky-10.2`). EL distros require point releases for `image-builder` compatibility. | Override to target a different distribution or version (e.g., `-e osbuild_distro=almalinux-10.2`). |
| `osbuild_arch` | `"x86_64"` | Target architecture (`x86_64` or `aarch64`). | Override for ARM-based builds (e.g., `-e osbuild_arch=aarch64`). |
| `osbuild_image_type` | `"minimal-installer"` (Fedora) or `"image-installer"` (EL) | Image type for `image-builder`. Fedora uses `minimal-installer`; EL distros use `image-installer`. | Override to build alternative formats (e.g., `qcow2`, `ami`, `vmdk`). |
| `osbuild_only_generate` | `true` | If `true`, generates a build script without executing it. If `false`, runs the build immediately. | Override to `-e osbuild_only_generate=false` to execute builds directly in the playbook. |
| `osbuild_build_bootc` | `false` | If `true`, builds a **bootc container image** instead of a traditional ISO. | Override to `-e osbuild_build_bootc=true` for atomic OS updates. |

### Backward Compatibility Notes
- **Deprecated variables** (e.g., `osbuild_blueprint_name`, `osbuild_blueprint_version`) are retained for compatibility but should be migrated to their modern equivalents.
- **Migration guidance**: Prefer `image-builder` CLI type mappings over legacy `osbuild_image_type` where possible.

**Sources**: [defaults/main.yml](defaults/main.yml#L8-L54)

---

## 2. Component Selection
Components are **modular building blocks** that define packages, services, repositories, and configurations for the final image. The `osbuild_components` list determines which components are included, while `osbuild_component_defs` defines their behavior.

### Component Selection Interface
```yaml
osbuild_components:
  - base
  - anaconda
  - gnome
  - sway
  - nvidia
  - development
  - container-tools
```
**Override example**:
```yaml
# In group_vars/workstation.yml
osbuild_components:
  - base
  - gnome
  - nvidia
  - cockpit
```

### Component Definitions Schema
Each component in `osbuild_component_defs` follows this schema:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `label` | String | Human-readable name. | `"GNOME Desktop"` |
| `packages` | List | Packages or Jinja2 expressions resolving to package lists. | `{{ system_packages.Settings.gnome }}` |
| `blueprint_groups` | List | DNF group names. | `["gnome-desktop"]` |
| `services` | List | Systemd services to enable. | `["gdm"]` |
| `kernel_args` | List | Kernel command-line arguments. | `["rd.driver.blacklist=nouveau"]` |
| `sources` | List | Repository sources required. | `["rpmfusion-nonfree-nvidia-driver"]` |
| `bootc_repos` | List | Shell commands to add repos in bootc builds. | See NVIDIA component below. |
| `requires` | List | Component dependencies. | `["base"]` |
| `conflicts` | List | Conflicting components. | `["sway"]` |
| `size_impact` | String | Estimated ISO size impact (`none`, `small`, `medium`, `large`). | `"large"` |
| `build_time_impact` | String | Estimated build time impact (`none`, `low`, `medium`, `high`). | `"high"` |
| `secure_boot_compatible` | Boolean | Secure Boot support. | `false` |
| `bootc_only` | Boolean | Applies only to bootc builds. | `false` |
| `blueprint_only` | Boolean | Applies only to ISO builds. | `true` |

### Example: NVIDIA Component
The `nvidia` component demonstrates **distro-aware repository management** and **kernel arguments**:
```yaml
nvidia:
  label: "NVIDIA GPU Stack"
  packages: "{{ system_packages.Graphics.nvidia }}"
  services:
    - nvidia-cdi-refresh
    - nvidia-persistenced
  kernel_args:
    - "rd.driver.blacklist=nouveau"
    - "modprobe.blacklist=nouveau"
    - "nvidia-drm.modeset=1"
  sources: "{{ _nvidia_sources }}"
  bootc_repos: "{{ _nvidia_bootc_repos }}"
  requires:
    - base
  size_impact: "large"
  secure_boot_compatible: false
```
**Distro-Aware Helpers**:
- `_nvidia_sources`: Dynamically selects Fedora or EL repository names based on `ansible_distribution`.
- `_nvidia_bootc_repos`: Generates repository definitions for bootc builds (e.g., RPM Fusion, CUDA, NVIDIA Container Toolkit).

**Sources**: [defaults/main.yml](defaults/main.yml#L152-L294)

---

## 3. Repository Sources
Repositories are **distro-specific** and derived from selected components. The `osbuild_sources` variable merges common distro sources with component-specific sources.

### Key Variables
| Variable | Description | Override Use Case |
|----------|-------------|-------------------|
| `osbuild_distro_sources_fedora` | Common Fedora sources (RPM Fusion, VS Code, Google Chrome). | Override to add/remove sources for Fedora builds. |
| `osbuild_distro_sources_el` | Common EL sources (EPEL, RPM Fusion EL, VS Code, Google Chrome). | Override for AlmaLinux/Rocky builds. |
| `osbuild_extra_repo_urls` | Additional repository URLs passed to `image-builder` as `--extra-repo`. | Override to add custom repositories (e.g., `-e osbuild_extra_repo_urls=['https://example.com/repo']`). |
| `osbuild_sources` | Merged list of distro and component sources. | Override to `[]` when the target distro differs from the build host. |

**Example**: Fedora sources include RPM Fusion and VS Code:
```yaml
osbuild_distro_sources_fedora:
  - rpmfusion-free
  - rpmfusion-free-updates
  - rpmfusion-nonfree
  - rpmfusion-nonfree-updates
  - vscode
  - google-chrome
```

**Sources**: [defaults/main.yml](defaults/main.yml#L574-L620)

---

## 4. Blueprint Configuration
Blueprints define the **final image composition** and can be generated dynamically (Jinja2) or statically (TOML).

### Key Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_use_blueprint_template` | `true` | If `true`, uses a Jinja2 template (`blueprint.toml.j2`). If `false`, uses a static TOML file. | Override to `-e osbuild_use_blueprint_template=false` for static blueprints. |
| `osbuild_static_blueprint_path` | Dynamic path (e.g., `files/fedora/43/x86_64/workstation/fedora-43-workstation-nvidia.toml`) | Path to static blueprint file. | Override to use a custom static blueprint. |
| `osbuild_blueprint_template` | `"blueprint.toml.j2"` | Path to Jinja2 template. | Override to use a custom template. |
| `osbuild_blueprint_components` | `[]` | Component files (packages, services, kernel args, repo URLs) merged with a static frame. Non-empty wins over the template and static path. | Select what goes into a static-style blueprint, e.g. `[base, anaconda, nvidia]`. |
| `osbuild_components_dir` | `<distro>/<ver>/<arch>/components` | Component file directory, relative to `files/`; follows `osbuild_distro`. | Point at a custom component set. |
| `osbuild_blueprint_frame_path` | `<distro>/<ver>/<arch>/frames/workstation.toml` | Non-composable blueprint part used with components. | Override to change firewall, locale, timezone or files. |
| `osbuild_target_distribution` | from `osbuild_distro` | Selects `vars/packages/<Name>.yml`: `fedora-*` → Fedora, `rocky-*` → Rocky, `almalinux-*` → AlmaLinux; otherwise the build host's distribution. | Rarely; set explicitly to force a taxonomy. |

### Dynamic vs. Static Blueprints
- **Dynamic**: Generated from `osbuild_component_defs` and user variables (e.g., `osbuild_extra_packages`).
- **Static**: Predefined TOML files for specific use cases (e.g., NVIDIA workstations).

**Sources**: [defaults/main.yml](defaults/main.yml#L622-L644)

---

## 5. User Customization
This section defines **default user accounts**, **system settings**, and **localization** for the installed system.

### Key Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_user_name` | `"osadmin"` | Default user account name. | Override to customize the admin username. |
| `osbuild_user_password` | Hashed password | Default user password (hashed). | Override with a new hashed password. |
| `osbuild_user_groups` | `["wheel", "libvirt"]` | User groups. | Override to add/remove groups (e.g., `["wheel", "docker"]`). |
| `osbuild_user_ssh_key` | `""` | SSH public key for the default user. | Override to inject an SSH key. |
| `osbuild_hostname` | `"workstation"` | System hostname. | Override to set a custom hostname. |
| `osbuild_timezone` | `"America/New_York"` | System timezone. | Override to set a different timezone. |
| `osbuild_keyboard` | `"us"` | Keyboard layout. | Override for non-US layouts. |
| `osbuild_locale` | `"en_US.UTF-8"` | System locale. | Override for non-English locales. |

**Example**: Override user settings in `group_vars`:
```yaml
osbuild_user_name: "devadmin"
osbuild_user_password: "$6$rounds=656000$abc123..."
osbuild_user_groups:
  - wheel
  - docker
```

**Sources**: [defaults/main.yml](defaults/main.yml#L646-L672)

---

## 6. Package Selection
Packages are **component-driven**, but additional packages can be included via `osbuild_extra_packages`. Version pinning is supported via `osbuild_package_pins`.

### Key Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_extra_packages` | `[]` | Additional packages beyond component defaults. | Override to add packages (e.g., `-e osbuild_extra_packages=['htop', 'tmux']`). |
| `osbuild_package_pins` | `{}` | Per-package version pins (e.g., `{"python3": "3.11.*"}`). | Override to pin versions for specific packages. |

**Example**: Pin CUDA toolkit version:
```yaml
osbuild_package_pins:
  cuda-toolkit: "13-4.*"
```

**Sources**: [defaults/main.yml](defaults/main.yml#L674-L699)

---

## 7. Kickstart and Firstboot Configuration
Kickstart files automate the **installation process**, while firstboot scripts run **post-installation** tasks.

### Kickstart Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_kickstart_enabled` | `true` | Enables kickstart automation. | Override to `-e osbuild_kickstart_enabled=false` for manual installation. |
| `osbuild_kickstart_partitioning` | `"auto"` | Disk partitioning mode (`auto` or `interactive`). | Override to `"interactive"` for manual partitioning. |
| `osbuild_kickstart_disk_min_gib` | `40` | Minimum disk size (GiB) for auto-partitioning. | Override for larger/smaller disks. |
| `osbuild_kickstart_sudoers` | `true` | Enables passwordless `sudo` for the `wheel` group. | Override to `false` to disable. |

**Auto-Partitioning Logic**:
1. `/` gets `root_percent` of usable space (minimum `root_min_gib`).
2. `spare` reserves `reserve_percent` for future volume growth.
3. `/usr` and `/var` share the remaining space (capped at `usr_max_gib` and `var_max_gib`).
4. `/home` is created only if remaining space ≥ `home_min_gib`.

**Sources**: [defaults/main.yml](defaults/main.yml#L718-L764)

### Firstboot Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_firstboot_enabled` | `true` | Enables firstboot scripts (e.g., dotfiles cloning via `yadm`). | Override to `-e osbuild_firstboot_enabled=false` to disable. |

**Sources**: [defaults/main.yml](defaults/main.yml#L718-L728)

---

## 8. Output Configuration
This section controls **where and how** build artifacts are stored.

### Key Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_output_dir` | `"/var/tmp/osbuild-images"` | Directory for final ISO/image. | Override to change the output location. |
| `osbuild_output_filename` | `"{{ osbuild_blueprint_name }}-{{ osbuild_distro }}.iso"` | Filename for the final image. | Override for custom naming. |
| `osbuild_container_tag` | `"localhost/{{ osbuild_blueprint_name }}:latest"` | Tag for bootc container images. | Override for custom container tags. |
| `osbuild_log_dir` | `"/var/tmp/osbuild-logs"` | Directory for build logs. | Override to change log location. |
| `osbuild_keep_logs` | `true` | Retains logs on failure. | Override to `false` to discard logs. |

**Sources**: [defaults/main.yml](defaults/main.yml#L708-L788)

---

## 9. Bootc Configuration (Container-Based OS Images)
Bootc enables **immutable, container-based OS images** for atomic updates. This section defines variables for bootc builds.

### Key Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_bootc_base_image` | `"quay.io/fedora/fedora-bootc:43"` | Base image for bootc builds. | Override to use Universal Blue images (e.g., `-e osbuild_bootc_base_image=ghcr.io/ublue-os/bluefin:stable`). |
| `osbuild_bootc_image_name` | `"quay.io/syncopated/{{ osbuild_blueprint_name }}"` | Container image name. | Override for custom registry paths. |
| `osbuild_bootc_image_tag` | `"latest"` | Container image tag. | Override for versioned tags. |
| `osbuild_bootc_build_disk_image` | `false` | Builds a bootable disk image (qcow2/ISO) from the container. | Override to `-e osbuild_bootc_build_disk_image=true`. |
| `osbuild_bootc_image_type` | `"qcow2"` | Disk image type (`qcow2`, `iso`, `raw`). | Override for alternative formats. |
| `osbuild_bootc_rootfs` | `"btrfs"` | Root filesystem type (`btrfs`, `ext4`, `xfs`). | Override for non-Btrfs filesystems. |

**Example**: Build a bootc image with a custom base:
```yaml
osbuild_build_bootc: true
osbuild_bootc_base_image: "ghcr.io/ublue-os/bluefin:stable"
osbuild_bootc_build_disk_image: true
```

**Sources**: [defaults/main.yml](defaults/main.yml#L806-L844)

---

## 10. Advanced Configuration
Advanced variables control **build-time behavior**, **logging**, and **resource constraints**.

### Key Variables
| Variable | Default Value | Description | Override Use Case |
|----------|---------------|-------------|-------------------|
| `osbuild_work_dir` | `"/var/lib/osbuild-composer"` | Work directory for `osbuild-composer`. | Override for custom work paths. |
| `osbuild_gpgkey_cache_dir` | `"{{ osbuild_work_dir }}/gpgkeys"` | Directory for cached GPG keys. | Override for custom GPG key storage. |
| `osbuild_min_disk_space` | `50` | Minimum free disk space (GiB) required for builds. | Override for resource-constrained environments. |
| `osbuild_verbose` | `false` | Enables verbose output. | Override to `-e osbuild_verbose=true` for debugging. |

**Sources**: [defaults/main.yml](defaults/main.yml#L790-L862)

---

## Override Strategies
### 1. **Playbook-Level Overrides**
Use `-e` (extra vars) to override defaults at runtime:
```bash
ansible-playbook playbooks/osbuild.yml -e osbuild_distro=almalinux-10.2 -e osbuild_components=['base','gnome']
```

### 2. **Inventory-Level Overrides**
Define variables in `group_vars` or `host_vars` for **environment-specific** configurations:
```yaml
# group_vars/workstation.yml
osbuild_components:
  - base
  - gnome
  - nvidia
  - cockpit
osbuild_kickstart_partitioning: "interactive"
```

### 3. **Role-Level Overrides**
Override defaults in the role's `vars/` directory (e.g., `vars/AlmaLinux.yml` for distro-specific packages).

### 4. **Blueprint-Level Overrides**
Use `osbuild_extra_packages` or `osbuild_package_pins` to customize package selection without modifying components.

---

## Architectural Patterns
### 1. **Component-Driven Design**
Components are **self-contained** and **composable**, enabling modular customization. For example:
- The `nvidia` component adds **GPU drivers**, **kernel arguments**, and **repositories** without affecting other components.
- The `gnome` component enables **GDM** and **GNOME packages** while conflicting with `sway`.

## 2. **Distro-Aware Logic**
Variables like `_nvidia_sources` and `_nvidia_bootc_repos` use **Jinja2 conditionals** to adapt to Fedora or EL distros:
```yaml
_nvidia_sources: >-
  {{ _is_fedora | ternary(
    ['rpmfusion-nonfree-nvidia-driver', 'cuda-fedora' + _distro_version + '-' + osbuild_arch],
    ['rpmfusion-nonfree-nvidia-driver', 'cuda-el' + _distro_major_version + '-x86_64']
  ) }}
```

### 3. **Immutable Defaults with Override Flexibility**
Defaults are **immutable** (defined in `defaults/main.yml`) but can be **overridden** at higher precedence levels (e.g., `group_vars`, `host_vars`, or `-e`).

---

## Next Steps
1. **[Build Modes: Selecting and Configuring for Your Use Case](8-build-modes-selecting-and-configuring-for-your-use-case)**: Learn how to choose between traditional ISO and bootc builds.
2. **[Managing Repositories and GPG Keys](10-managing-repositories-and-gpg-keys)**: Dive deeper into repository management and GPG key handling.
3. **[Template Files: Structure and Customization](11-template-files-structure-and-customization)**: Explore how Jinja2 templates generate blueprints dynamically.
4. **[Distribution-Specific Variables and Configurations](18-distribution-specific-variables-and-configurations)**: Understand how variables are tailored for AlmaLinux, Fedora, and Rocky.

**Sources**: [defaults/main.yml](defaults/main.yml#L1-L862)