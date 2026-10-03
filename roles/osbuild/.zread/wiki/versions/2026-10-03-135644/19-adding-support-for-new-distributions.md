This document provides a **systematic, pattern-driven methodology** for extending the **OSBuild Ansible role** to support new Linux distributions. It is structured to guide advanced developers through the **architectural patterns, variable hierarchies, and integration touchpoints** that define distribution support in this role.

The role is designed around a **component-based, declarative configuration system** where distributions are defined through **YAML variable files, Jinja2 templates, and task-level logic**. This design ensures that adding a new distribution is a **predictable, repeatable process** that aligns with the existing patterns for Fedora, AlmaLinux, and Rocky Linux.

---

## 1. Architectural Overview: How Distributions Are Modeled

The OSBuild role uses a **four-layered configuration model** to define distribution support:

1. **Default Variables and Interfaces (`defaults/main.yml`)**
   Global defaults, component selection interface (`osbuild_components`), and component definitions (`osbuild_component_defs`) that map high-level features to categorized package sets.

2. **Canonical Package Taxonomy (`vars/packages/<Distribution>.yml` and `00-distributions.yml`)**
   Defined in the repository root, these files serve as the single source of truth for distribution package names (`system_packages`, `system_groups`, `system_flatpaks`, `system_copr_repos`). Mappings for distribution-specific package and repository naming differences are maintained in `00-distributions.yml`. The Python utility [`scripts/package_tracker.py`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/scripts/package_tracker.py) maintains these files and generates build manifests.

3. **Distribution-Specific Repository Variables (`vars/<Distribution>.yml`)**
   Located in the role's `vars/` directory, these define repository endpoints (`repo` dictionary with `baseurl`, `metalink`, `gpgkey_url`, `check_gpg`), GPG key locations, and distribution-specific component overrides.

4. **Templates and Tasks**
   Jinja2 templates for blueprints, repository configurations (`templates/etc/osbuild-composer/repositories/<distribution>-<version>.json.j2`), and kickstart files, alongside Ansible tasks that resolve variables into build artifacts.

This model ensures **separation of concerns**: repository definitions, package taxonomies, and build logic are cleanly decoupled.

**Key Insight**:
> *Supporting a new distribution does not require modifying core tasks or templates. Instead, you define a repository variable file, establish a package taxonomy file (or mapping in `00-distributions.yml`), create a repository template, and reference the new distribution in the global defaults.*

---

## 2. Step-by-Step Process for Adding a New Distribution

### Step 1: Create a Distribution Variable File

**Location**: `vars/<Distribution>.yml`
**Purpose**: Define repositories, GPG keys, and compatibility logic.

#### Required Structure

```yaml
# SPDX-License-Identifier: MIT-0
---
repo:
  <repo-name>:
    baseurl: "https://mirror.example.com/path/to/repo"
    gpgkey_url: "file:///usr/share/distribution-gpg-keys/example/RPM-GPG-KEY-Example-10"
    check_gpg: true
  <another-repo>:
    metalink: "https://mirrors.example.com/metalink?repo=appstream-10&arch=x86_64"
    gpgkey_url: "https://example.com/keys/RPM-GPG-KEY-Example-10"
    check_gpg: true
```

#### Key Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `baseurl` | string | Direct URL to repository | `https://dl.example.com/repo` |
| `metalink` | string | Mirror list URL | `https://mirrors.example.com/metalink?repo=baseos-10` |
| `gpgkey_url` | string | URL or `file://` path to GPG key | `file:///usr/share/distribution-gpg-keys/example/KEY` |
| `check_gpg` | boolean | Whether to verify packages | `true` |

#### Example: OpenSUSE Leap 15.6

```yaml
repo:
  opensuse-base:
    baseurl: "https://download.opensuse.org/distribution/leap/15.6/repo/oss/"
    gpgkey_url: "file:///usr/share/distribution-gpg-keys/opensuse/RPM-GPG-KEY-opensuse-15.6"
    check_gpg: true
  opensuse-update:
    baseurl: "https://download.opensuse.org/update/leap/15.6/oss/"
    gpgkey_url: "file:///usr/share/distribution-gpg-keys/opensuse/RPM-GPG-KEY-opensuse-15.6"
    check_gpg: true
  packman:
    baseurl: "https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Leap_15.6/"
    gpgkey_url: "https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Leap_15.6/repodata/repomd.xml.key"
    check_gpg: true
```

**Sources**:
- [Fedora.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/Fedora.yml#L1-L78)
- [AlmaLinux.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/AlmaLinux.yml#L1-L67)
- [Rocky.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/Rocky.yml#L1-L89)

---

### Step 2: Create a Repository Template for `osbuild-composer`

**Location**: `templates/etc/osbuild-composer/repositories/<distribution>-<version>.json.j2`
**Purpose**: Generate a JSON configuration file for `osbuild-composer` that defines the repositories for the target distribution.

#### Template Structure

```jinja2
{
    "x86_64": [
        {% for repo_name, repo_data in repo.items() %}
        {
            "name": "{{ repo_name }}",
            "check_gpg": {{ repo_data.check_gpg | to_json }},
            {% if repo_data.metalink is defined %}
            "metalink": "{{ repo_data.metalink }}"
            {% else %}
            "baseurl": "{{ repo_data.baseurl }}"
            {% endif %}
            {% if repo_gpgkeys is defined and repo_name in repo_gpgkeys %}
            ,"gpgkey": {{ repo_gpgkeys[repo_name] | to_json }}
            {% endif %}
        }{{ "," if not loop.last else "" }}
        {% endfor %}
    ]
}
```

#### Example: OpenSUSE Leap 15.6

```jinja2
{
    "x86_64": [
        {
            "name": "opensuse-base",
            "check_gpg": true,
            "baseurl": "https://download.opensuse.org/distribution/leap/15.6/repo/oss/"
        },
        {
            "name": "opensuse-update",
            "check_gpg": true,
            "baseurl": "https://download.opensuse.org/update/leap/15.6/oss/"
        },
        {
            "name": "packman",
            "check_gpg": true,
            "baseurl": "https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Leap_15.6/"
        }
    ]
}
```

**Sources**:
- [fedora-43.json.j2](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/templates/etc/osbuild-composer/repositories/fedora-43.json.j2#L1-L20)
- [almalinux-10.json.j2](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/templates/etc/osbuild-composer/repositories/almalinux-10.json.j2#L1-L20)
- [rocky-9.json.j2](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/templates/etc/osbuild-composer/repositories/rocky-9.json.j2#L1-L30)

---

### Step 3: Update `defaults/main.yml` for Distribution Awareness

The `defaults/main.yml` file contains **global logic** that must recognize the new distribution. Key areas to update:

#### 3.1. Build Host Packages

Add the new distribution to the `osbuild_host_packages` dictionary:

```yaml
osbuild_host_packages:
  Fedora:
    - osbuild
    - image-builder
    - bash-completion
  AlmaLinux:
    - osbuild
    - image-builder
  Rocky:
    - osbuild
    - image-builder
  OpenSUSE:
    - osbuild
    - kiwi
    - bash-completion
```

#### 3.2. Common Repository Sources

Add the new distribution to the `osbuild_distro_sources_*` logic:

```yaml
osbuild_distro_sources_fedora:
  - rpmfusion-free
  - rpmfusion-free-updates
osbuild_distro_sources_el:
  - epel
  - rpmfusion-free-updates
osbuild_distro_sources_opensuse:
  - packman
```

#### 3.3. Image Type Mapping

Update the `osbuild_image_type` logic to handle the new distribution:

```yaml
osbuild_image_type: >-
  {{
    'minimal-installer' if ansible_distribution == 'Fedora'
    else 'image-installer' if ansible_distribution in ['AlmaLinux', 'Rocky']
    else 'oem' if ansible_distribution == 'OpenSUSE'
    else 'image-installer'
  }}
```

**Sources**:
- [defaults/main.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/defaults/main.yml#L40-L60)
- [defaults/main.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/defaults/main.yml#L200-L220)

---

### Step 4: Define Package Taxonomy in Repository Root

Package taxonomies for distributions are defined in `vars/packages/<Distribution>.yml` located in the **repository root** (e.g., [`vars/packages/Fedora.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/Fedora.yml)), outside the role directory. These files serve as the canonical source of truth for package definitions and are loaded dynamically by the role in [`tasks/main.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/tasks/main.yml#L60-L68):

```yaml
- name: Load package taxonomy
  ansible.builtin.include_vars:
    file: "{{ role_path }}/../../vars/packages/{{ osbuild_target_distribution }}.yml"
```

#### Taxonomy Structure

Package taxonomies follow the **XDG Desktop Entry Specification** registered categories (`System`, `Settings`, `Graphics`, `AudioVideo`, `Development`, `Utility`):
- `system_packages`: Native package definitions organized by category and subcategory.
- `system_groups`: DNF/comps group lists.
- `system_flatpaks`: Application IDs.
- `system_copr_repos`: COPR repository declarations.
- Package versions are never pinned in taxonomy files (all resolve to `*`). Versions are pinned separately using `osbuild_package_pins` in `defaults/main.yml` or host/group vars.

#### Example: `vars/packages/OpenSUSE.yml`

```yaml
---
# Canonical Package Taxonomy for OpenSUSE
system_packages:
  System:
    kernel:
      - kernel-default
    base:
      - bash
      - coreutils
      - systemd
      - rsync
    installer:
      - kiwi
    ansible:
      - ansible-core
    networking:
      - NetworkManager
      - firewalld
  Settings:
    gnome:
      - gnome-shell
      - gdm
    sway_core:
      - sway
      - waybar
  Development:
    compilers:
      - gcc
      - make
    languages:
      - python3
      - nodejs
system_groups:
  base:
    - base
system_flatpaks: {}
system_copr_repos: {}
```

#### Cross-Distribution Package Mappings (`00-distributions.yml`)

When package names diverge across distributions (e.g., `ansible` in Fedora vs. `ansible-core` in EL/OpenSUSE), record the differences in [`vars/packages/00-distributions.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/00-distributions.yml):

```yaml
package_mappings:
  ansible:
    fedora: ansible
    rhel: ansible-core
    almalinux: ansible-core
    rocky: ansible-core
    opensuse: ansible-core
```

#### Maintaining Taxonomies with `scripts/package_tracker.py`

Package taxonomies can be maintained manually or managed using the [`scripts/package_tracker.py`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/scripts/package_tracker.py) tool:

1. **Interactive TUI Mode**:
   Launch the terminal interface to inspect, search, add, or remove packages, as well as generate build manifests:
   ```bash
   python3 scripts/package_tracker.py tui
   ```

2. **CLI Subcommands**:
   - **Add package**:
     ```bash
     python3 scripts/package_tracker.py add --distro OpenSUSE --category System --subcategory kernel --package "kernel-default"
     ```
   - **Add package across all distributions** (automatically resolves names using `00-distributions.yml` mappings):
     ```bash
     python3 scripts/package_tracker.py add --distro All --category Development --subcategory compilers --package "gcc"
     ```
   - **Search taxonomy**:
     ```bash
     python3 scripts/package_tracker.py search kernel
     ```
   - **List categories and counts**:
     ```bash
     python3 scripts/package_tracker.py list --distro OpenSUSE
     ```
   - **Generate build manifest**:
     ```bash
     python3 scripts/package_tracker.py build --distro OpenSUSE --blueprint workstation --subcategories "base,kernel,networking"
     ```

**Sources**:
- [vars/packages/Fedora.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/Fedora.yml#L1-L627)
- [vars/packages/AlmaLinux.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/AlmaLinux.yml#L1-L616)
- [vars/packages/Rocky.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/Rocky.yml#L1-L622)
- [vars/packages/00-distributions.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/00-distributions.yml#L1-L108)
- [package_tracker.py](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/scripts/package_tracker.py#L1-L825)

---

### Step 5: Update Component Definitions for Distribution Compatibility

The `osbuild_component_defs` dictionary in `defaults/main.yml` may require **distribution-specific overrides** for certain components (e.g., NVIDIA drivers).

#### Example: NVIDIA Component for OpenSUSE

```yaml
nvidia:
  label: "NVIDIA GPU Stack"
  packages: "{{ system_packages.Graphics.nvidia_opensuse }}"
  services:
    - nvidia-persistenced
  kernel_args:
    - "rd.driver.blacklist=nouveau"
    - "modprobe.blacklist=nouveau"
    - "nvidia-drm.modeset=1"
  sources: ["nvidia-tumbleweed"]
  bootc_repos: "{{ _nvidia_bootc_repos_opensuse }}"
```

**Sources**:
- [defaults/main.yml (component definitions)](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/defaults/main.yml#L213-L500)

---

### Step 6: Test and Validate the New Distribution

#### 6.1. Run a Build

```bash
ansible-playbook playbooks/osbuild.yml -e osbuild_distro=opensuse-15.6 -e osbuild_arch=x86_64
```

#### 6.2. Validate the Blueprint

Check the generated blueprint in `osbuild_output_dir`:

```bash
cat /var/tmp/osbuild-images/custom.toml
```

#### 6.3. Validate the Repository Template

Check the generated repository JSON:

```bash
cat /var/tmp/osbuild-images/repositories/opensuse-15.6.json
```

#### 6.4. Run Tests

Add test cases to the **BATS** and **Python** test suites in the `tests/` directory.

**Sources**:
- [validate_build_modes.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/tests/validate_build_modes.yml)
- [kickstart.bats](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/tests/kickstart/kickstart.bats)

---

## 3. Key Integration Points

### 3.1. Variable Resolution Flow

The following diagram illustrates how variables are resolved for a new distribution:

```mermaid
flowchart TD
    A["defaults/main.yml"] -->|osbuild_distro| B["roles/osbuild/vars/<Distribution>.yml"]
    A -->|osbuild_target_distribution| P["vars/packages/<Distribution>.yml"]
    B -->|repo| C["templates/etc/osbuild-composer/repositories/<distribution>.json.j2"]
    C -->|JSON| D["osbuild-composer --extra-repo"]
    A -->|osbuild_components| E["osbuild_component_defs"]
    P -->|system_packages| E
    E -->|packages, groups| F["blueprint.toml.j2"]
    F -->|TOML| G["image-builder build"]
    P -.->|maintained by| T["scripts/package_tracker.py"]
```

### 3.2. Task-Level Integration

The following tasks are **distribution-agnostic** and will automatically support the new distribution:

| Task File | Purpose | Key Variables Used |
|-----------|---------|--------------------|
| `tasks/select_build_mode.yml` | Resolves build mode (ISO, bootc, generate-only) | `osbuild_build_bootc`, `osbuild_only_generate` |
| `tasks/sources.yml` | Builds repository URL list | `osbuild_sources`, `osbuild_extra_repo_urls` |
| `tasks/repo_keys.yml` | Fetches GPG keys | `repo[*].gpgkey_url` |
| `tasks/blueprint.yml` | Renders blueprint.toml | `osbuild_components`, `osbuild_component_defs` |

**Sources**:
- [tasks/select_build_mode.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/tasks/select_build_mode.yml#L1-L20)
- [tasks/sources.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/tasks/sources.yml#L1-L30)
- [tasks/repo_keys.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/tasks/repo_keys.yml#L1-L50)
- [tasks/blueprint.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/tasks/blueprint.yml#L1-L50)

---

## 4. Common Pitfalls and Mitigations

| Pitfall | Description | Mitigation |
|---------|-------------|------------|
| **GPG Key Mismatch** | `osbuild-composer` fails if the GPG key is invalid or missing. | Always verify keys with `curl -sSL <gpgkey_url> \| gpg --show-keys`. |
| **Repository 404** | Metalink/baseurl returns 404. | Use `curl -I <url>` to verify repository availability. |
| **Package Not Found** | Package names differ across distributions. | Use `dnf search <package>` or `zypper search <package>` to verify. |
| **Image Type Unsupported** | `osbuild-composer` does not support the image type for the new distribution. | Check `image-builder list` on the build host for supported types. |
| **Variable Shadowing** | Global variables override distribution-specific ones. | Use `ansible-playbook -e "@vars/<Distribution>.yml"` to test. |

---

## 5. Next Steps

1. **Review Existing Patterns**: Study the distribution variable files ([`Fedora.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/Fedora.yml), [`AlmaLinux.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/AlmaLinux.yml), and [`Rocky.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/Rocky.yml)) as well as the canonical package taxonomies in [`vars/packages/Fedora.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/Fedora.yml), [`vars/packages/AlmaLinux.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/AlmaLinux.yml), [`vars/packages/Rocky.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/Rocky.yml), and [`vars/packages/00-distributions.yml`](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/00-distributions.yml).
2. **Test Incrementally**: Start with a minimal `vars/<Distribution>.yml` file and a corresponding `vars/packages/<Distribution>.yml`, adding complexity as needed.
3. **Validate with CI**: Add test cases to the [Testing Framework: BATS and Python Tests](20-testing-framework-bats-and-python-tests) page.
4. **Document**: Update the [Overview of Supported Linux Distributions](17-overview-of-supported-linux-distributions-almalinux-fedora-rocky) page to include the new distribution.

**Sources**:
- [defaults/main.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/defaults/main.yml#L1-L903)
- [vars/Fedora.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/Fedora.yml#L1-L78)
- [vars/AlmaLinux.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/AlmaLinux.yml#L1-L67)
- [vars/Rocky.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/roles/osbuild/vars/Rocky.yml#L1-L89)
- [vars/packages/Fedora.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/Fedora.yml#L1-L627)
- [vars/packages/AlmaLinux.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/AlmaLinux.yml#L1-L616)
- [vars/packages/Rocky.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/Rocky.yml#L1-L622)
- [vars/packages/00-distributions.yml](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/vars/packages/00-distributions.yml#L1-L108)
- [package_tracker.py](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/scripts/package_tracker.py#L1-L825)