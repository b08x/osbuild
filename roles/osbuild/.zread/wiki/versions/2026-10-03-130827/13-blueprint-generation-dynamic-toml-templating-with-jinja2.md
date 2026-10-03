This page explains how the **osbuild** Ansible role dynamically generates TOML-based blueprints for OS image builds using **Jinja2 templating**. The blueprint is the foundational configuration file for `image-builder-cli` and `bootc-image-builder`, defining packages, services, kernel arguments, and customizations. The role employs a **component-based design** to modularize and reuse configurations across distributions (Fedora, AlmaLinux, Rocky Linux) and build modes (traditional ISO, bootc container).

---

## Architectural Overview

The blueprint generation system follows a **three-tier architecture**:
1. **Data Layer**: Component definitions (`osbuild_component_defs`) in [`defaults/main.yml`](defaults/main.yml#L200-L866) provide the structured data model for packages, services, kernel arguments, and files.
2. **Templating Layer**: Jinja2 templates (`.j2` files) in [`templates/`](templates/) render TOML configurations dynamically.
3. **Orchestration Layer**: The [`tasks/blueprint.yml`](tasks/blueprint.yml#L1-L130) task renders templates, injects first-boot and kickstart configurations, and validates the output.

### Mermaid Architecture Diagram
```mermaid
flowchart TD
    A[Component Definitions\n(defaults/main.yml)] -->|Data Model| B[Jinja2 Templates\n(templates/*.j2)]
    B -->|Rendered TOML| C[Blueprint File\n(blueprint.toml)]
    C --> D[image-builder-cli\nor bootc-image-builder]
    D --> E[OS Image\n(ISO or Container)]

    subgraph Templating Layer
        B1[blueprint.toml.j2\n(Main Blueprint)]
        B2[disk.toml.j2\n(Disk Config)]
        B3[iso.toml.j2\n(ISO Config)]
        B4[kickstart.toml.j2\n(Kickstart Injection)]
        B5[firstboot-files.toml.j2\n(First-Boot Files)]
        B6[Containerfile.bootc.j2\n(Bootc Multi-Stage)]
    end

    subgraph Orchestration Layer
        C1[tasks/blueprint.yml\n(Render + Inject)]
        C2[tasks/bootc.yml\n(Bootc Workflow)]
        C3[tasks/select_build_mode.yml\n(Mode Selection)]
    end

    C1 --> B1
    C1 --> B4
    C1 --> B5
    C2 --> B2
    C2 --> B3
    C2 --> B6
    C3 --> C1
    C3 --> C2
```

Sources: [defaults/main.yml](defaults/main.yml#L200-L866), [tasks/blueprint.yml](tasks/blueprint.yml#L1-L130), [tasks/bootc.yml](tasks/bootc.yml#L1-L134), [tasks/select_build_mode.yml](tasks/select_build_mode.yml#L1-L33)

---

## Core Templating Mechanism

### Primary Blueprint Template: `blueprint.toml.j2`
The **primary template** [`templates/blueprint.toml.j2`](templates/blueprint.toml.j2#L1-L133) dynamically generates the `blueprint.toml` file for `image-builder-cli`. It includes:
- **Metadata**: Blueprint name, description, version, and target distribution.
- **Package Groups**: DNF groups derived from selected components (e.g., `development-tools`, `container-management`).
- **Packages**: Individual packages from components and `osbuild_extra_packages`, with version pinning via `osbuild_package_pins`.
- **Kernel Arguments**: Aggregated from component definitions (e.g., NVIDIA-specific `rd.driver.blacklist=nouveau`).
- **Services**: Systemd services to enable (e.g., `gdm`, `nvidia-persistenced`).
- **Timezone & Locale**: Configured via `osbuild_timezone`, `osbuild_locale`, and `osbuild_keyboard`.
- **File Injections**: Custom files (e.g., NVIDIA CDI scripts, first-boot splash) embedded as TOML literal strings.
- **Installer Modules**: Enables Anaconda modules (e.g., `Users`) and disables unnecessary ones (e.g., `Subscription`).

#### Example: Dynamic Package Injection
```toml
# Generated from blueprint.toml.j2
[[packages]]
name = "kernel-devel"
version = "*"

[[packages]]
name = "nvidia-driver"
version = "550.90.07"
```
Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L1-L133)

---

### Template Hierarchy for Build Modes
The role supports **two build modes**, each with distinct TOML templates:

| **Build Mode**          | **Primary Template**       | **Additional Templates**                     | **Use Case**                          |
|-------------------------|----------------------------|---------------------------------------------|---------------------------------------|
| Traditional ISO         | `blueprint.toml.j2`        | `kickstart.toml.j2`, `firstboot-files.toml.j2` | Anaconda-based installer images       |
| Bootc Container         | `Containerfile.bootc.j2`   | `disk.toml.j2`, `iso.toml.j2`                | Immutable container images with `bootc`|

#### Traditional ISO Mode
- **Primary Output**: `blueprint.toml` (rendered from `blueprint.toml.j2`).
- **Injections**:
  - **Kickstart**: Appended via [`kickstart.toml.j2`](templates/kickstart.toml.j2#L1-L12) for automated installations.
  - **First-Boot Files**: Appended via [`firstboot-files.toml.j2`](templates/firstboot-files.toml.j2#L1-L11) for post-install automation.
  - **Sudoers**: Appended via [`kickstart-sudoers.toml.j2`](templates/kickstart-sudoers.toml.j2) for passwordless sudo.

#### Bootc Container Mode
- **Primary Output**: `Containerfile` (rendered from [`Containerfile.bootc.j2`](templates/Containerfile.bootc.j2#L1-L128)) for multi-stage builds.
- **Additional TOML Configs**:
  - **Disk Configuration**: [`disk.toml.j2`](templates/disk.toml.j2#L1-L27) defines filesystem layouts (e.g., `/`, `/home`).
  - **ISO Configuration**: [`iso.toml.j2`](templates/iso.toml.j2#L1-L32) defines Anaconda installer modules for bootc installer images.

Sources: [tasks/blueprint.yml](tasks/blueprint.yml#L1-L130), [tasks/bootc.yml](tasks/bootc.yml#L1-L134), [templates/Containerfile.bootc.j2](templates/Containerfile.bootc.j2#L1-L128)

---

## Data Model: Component Definitions
The **component system** is the backbone of the blueprint generation. Each component (e.g., `nvidia`, `gnome`, `development`) defines:
- **Packages**: Lists of RPM packages to include.
- **Blueprint Groups**: DNF group names (e.g., `c-development`).
- **Services**: Systemd services to enable.
- **Kernel Arguments**: Boot-time kernel parameters.
- **Files**: Custom file payloads (e.g., scripts, configs).
- **Sources**: Repository sources required for the component.
- **Dependencies/Conflicts**: Component relationships (e.g., `nvidia` requires `base`).

### Example: NVIDIA Component Definition
```yaml
# From defaults/main.yml
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
  requires:
    - base
  conflicts: []
  size_impact: "large"
  build_time_impact: "medium"
  secure_boot_compatible: false
```
Sources: [defaults/main.yml](defaults/main.yml#L260-L280)

---

## Templating Workflow

### Step 1: Mode Selection
The [`tasks/select_build_mode.yml`](tasks/select_build_mode.yml#L1-L33) task resolves the build mode into one of:
- `generate_only`: Generate blueprint and build script (default for traditional ISO).
- `traditional_iso`: Generate blueprint and build the image.
- `bootc_image`: Build a bootc container image.

### Step 2: Template Rendering
The [`tasks/blueprint.yml`](tasks/blueprint.yml#L1-L130) task:
1. **Renders the primary template** (`blueprint.toml.j2` or static blueprint) to `osbuild_output_dir`.
2. **Injects first-boot files** (if `osbuild_firstboot_enabled` is true) via `firstboot-files.toml.j2`.
3. **Injects kickstart configuration** (if `osbuild_kickstart_enabled` is true) via `kickstart.toml.j2`.
4. **Injects sudoers configuration** (if `osbuild_kickstart_sudoers` is true) via `kickstart-sudoers.toml.j2`.
5. **Validates TOML syntax** (optional, requires `python3-tomli`).

### Step 3: Bootc-Specific Workflow
For `bootc_image` mode, the [`tasks/bootc.yml`](tasks/bootc.yml#L1-L134) task:
1. Renders the `Containerfile.bootc.j2` template.
2. Renders `disk.toml.j2` and `iso.toml.j2` for disk/ISO configurations.
3. Builds the container image using `podman` and optionally builds a bootable disk image.

Sources: [tasks/blueprint.yml](tasks/blueprint.yml#L1-L130), [tasks/bootc.yml](tasks/bootc.yml#L1-L134), [tasks/select_build_mode.yml](tasks/select_build_mode.yml#L1-L33)

---

## Dynamic Variable Injection
The templating system leverages **Ansible variables** to customize the blueprint dynamically. Key variables include:

| **Variable**                     | **Purpose**                                                                 | **Source**                          |
|----------------------------------|-----------------------------------------------------------------------------|-------------------------------------|
| `osbuild_components`             | List of selected components (e.g., `base`, `nvidia`, `gnome`).            | [`defaults/main.yml`](defaults/main.yml#L180-L195) |
| `osbuild_component_defs`         | Dictionary of component definitions (packages, services, etc.).          | [`defaults/main.yml`](defaults/main.yml#L200-L866) |
| `osbuild_blueprint_name`         | Name of the blueprint (e.g., `custom`).                                    | [`defaults/main.yml`](defaults/main.yml#L15-L17) |
| `osbuild_distro`                 | Target distribution (e.g., `fedora-43`).                                  | [`defaults/main.yml`](defaults/main.yml#L10-L12) |
| `osbuild_package_pins`           | Version pins for packages (e.g., `nvidia-driver: "550.90.07"`).           | User-defined (default: `*`)         |
| `osbuild_timezone`               | System timezone (e.g., `America/New_York`).                                | User-defined (default: `UTC`)       |
| `osbuild_locale`                 | System locale (e.g., `en_US.UTF-8`).                                       | User-defined (default: `en_US.UTF-8`)|
| `osbuild_kickstart_enabled`     | Enable kickstart injection.                                               | User-defined (default: `true`)      |
| `osbuild_firstboot_enabled`      | Enable first-boot file injection.                                         | User-defined (default: `true`)      |

### Example: Variable Usage in Templates
```jinja2
# From blueprint.toml.j2
name = "{{ osbuild_blueprint_name }}"
distro = "{{ osbuild_distro }}"

{% for c in osbuild_components %}
{% if c in osbuild_component_defs and osbuild_component_defs[c].packages is defined %}
{%   for package in osbuild_component_defs[c].packages %}
[[packages]]
name = "{{ package }}"
version = "{{ osbuild_package_pins.get(package, '*') }}"
{%   endfor %}
{% endif %}
{% endfor %}
```
Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L1-L133), [defaults/main.yml](defaults/main.yml#L10-L195)

---

## Validation and Error Handling
The blueprint generation process includes **runtime validation** to ensure correctness:
1. **TOML Syntax Validation**:
   - Uses `python3-tomllib` (Python ≥ 3.11) or `tomli` (Python < 3.11) to validate the generated TOML.
   - Skipped if `python3-tomli` is not installed (graceful degradation).
2. **Kickstart Conflict Detection**:
   - Checks for conflicts between blueprint settings and kickstart (e.g., `[[customizations.user]]`).
3. **First-Boot File Validation**:
   - Ensures first-boot files do not contain `'''` (TOML literal string delimiter).
4. **Component Validation**:
   - Validates component dependencies and conflicts via [`tasks/validate_components.yml`](tasks/validate_components.yml).

Sources: [tasks/blueprint.yml](tasks/blueprint.yml#L115-L130), [tasks/validate_components.yml](tasks/validate_components.yml)

---
## Template Inclusion and Reusability
The templating system supports **nested template inclusion** for modularity:
- **Snippets**: Reusable code blocks (e.g., [`snippets/nvidia-cdi.sh.j2`](templates/snippets/nvidia-cdi.sh.j2)) are included in other templates.
- **Systemd Units**: Templates like [`systemd/nvidia-cdi-refresh.service.j2`](templates/systemd/nvidia-cdi-refresh.service.j2) are embedded in the blueprint.

### Example: NVIDIA CDI Injection
```jinja2
# From blueprint.toml.j2
{% if 'nvidia' in osbuild_components %}
[[customizations.files]]
path = "/usr/local/bin/nvidia-cdi-generate.sh"
mode = "0755"
data = '''
{% include 'snippets/nvidia-cdi.sh.j2' %}'''
{% endif %}
```
Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L110-L133), [templates/snippets/nvidia-cdi.sh.j2](templates/snippets/nvidia-cdi.sh.j2)

---
## Build Mode Comparison
The following table compares the templating behavior across build modes:

| **Feature**               | **Traditional ISO**                          | **Bootc Container**                        |
|---------------------------|---------------------------------------------|--------------------------------------------|
| **Primary Template**      | `blueprint.toml.j2`                         | `Containerfile.bootc.j2`                   |
| **Output**                | `blueprint.toml`                            | `Containerfile` + `disk.toml`/`iso.toml`    |
| **Kickstart Injection**   | Yes (via `kickstart.toml.j2`)               | No (handled by `bootc-image-builder`)      |
| **First-Boot Injection**  | Yes (via `firstboot-files.toml.j2`)         | No (handled by container entrypoint)       |
| **Disk Config**           | No                                          | Yes (via `disk.toml.j2`)                   |
| **Multi-Stage Build**     | No                                          | Yes (3 stages in `Containerfile`)          |
| **Ansible Role Inversion**| No                                          | Yes (build-time Ansible in stage 2)        |

Sources: [tasks/blueprint.yml](tasks/blueprint.yml#L1-L130), [tasks/bootc.yml](tasks/bootc.yml#L1-L134)

---
## Practical Examples

### Example 1: Adding a Custom Component
To add a new component (e.g., `docker`):
1. **Define the Component** in `defaults/main.yml`:
   ```yaml
   osbuild_component_defs:
     docker:
       label: "Docker CE"
       packages: "{{ system_packages.System.docker }}"
       services: ["docker"]
       sources: ["docker-ce-stable"]
       requires: ["base"]
       conflicts: []
   ```
2. **Add to `osbuild_components`**:
   ```yaml
   osbuild_components:
     - base
     - docker
   ```
3. **Render the Blueprint**:
   The `blueprint.toml.j2` template will automatically include Docker packages and enable the `docker` service.

Sources: [defaults/main.yml](defaults/main.yml#L200-L866)

---
### Example 2: Customizing Kernel Arguments
To add custom kernel arguments for a component:
1. **Update the Component Definition**:
   ```yaml
   osbuild_component_defs:
     custom:
       kernel_args:
         - "mitigations=off"
         - "console=ttyS0"
   ```
2. **Add to `osbuild_components`**:
   ```yaml
   osbuild_components:
     - base
     - custom
   ```
3. **Result in `blueprint.toml`**:
   ```toml
   [customizations.kernel]
   append = "rd.driver.blacklist=nouveau mitigations=off console=ttyS0"
   ```

Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L40-L50)

---
## Key Files and Their Roles

| **File**                          | **Role**                                                                                     |
|-----------------------------------|---------------------------------------------------------------------------------------------|
| [`blueprint.toml.j2`](templates/blueprint.toml.j2) | Primary template for traditional ISO blueprints.                                            |
| [`Containerfile.bootc.j2`](templates/Containerfile.bootc.j2) | Multi-stage Containerfile for bootc builds.                                                 |
| [`disk.toml.j2`](templates/disk.toml.j2) | Filesystem configuration for bootc disk images.                                            |
| [`iso.toml.j2`](templates/iso.toml.j2) | Anaconda installer configuration for bootc ISO images.                                    |
| [`kickstart.toml.j2`](templates/kickstart.toml.j2) | Kickstart configuration for automated installations.                                       |
| [`firstboot-files.toml.j2`](templates/firstboot-files.toml.j2) | First-boot splash and scripts.                                                              |
| [`tasks/blueprint.yml`](tasks/blueprint.yml) | Orchestrates blueprint rendering and injections.                                            |
| [`tasks/bootc.yml`](tasks/bootc.yml) | Orchestrates bootc container and disk image builds.                                         |
| [`defaults/main.yml`](defaults/main.yml) | Defines component system and default variables.                                             |

---
## Next Steps
To deepen your understanding of the **Blueprint Generation** system, explore the following pages:
- **[Component System: Modular Package and Configuration Management](10-component-system-modular-package-and-configuration-management)**: Learn how components are structured and validated.
- **[Traditional ISO Build Workflow with image-builder-cli](11-traditional-iso-build-workflow-with-image-builder-cli)**: Understand how the blueprint is used in ISO builds.
- **[Bootc Container Image Build Process and Multi-Stage Containerfile](12-bootc-container-image-build-process-and-multi-stage-containerfile)**: Explore the bootc-specific templating and build process.
- **[First-Boot Automation with Embedded Ansible Playbooks](17-first-boot-automation-with-embedded-ansible-playbooks)**: See how first-boot configurations are injected into the blueprint.

For hands-on customization, refer to:
- **[Configuring Build Host Requirements and Dependencies](3-configuring-build-host-requirements-and-dependencies)**
- **[Selecting Target Distribution and Architecture](4-selecting-target-distribution-and-architecture)**