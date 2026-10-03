This guide provides a step-by-step introduction to setting up and running your first custom Linux image build using the **OSBuild** role. By the end of this guide, you will have generated a build script or executed a build directly, depending on your configuration.

This guide assumes you are working on a **Fedora, AlmaLinux, or Rocky Linux** build host and have **Ansible** installed. If you haven't installed Ansible or verified your system requirements, refer to the **[Prerequisites: System Requirements and Dependencies](3-prerequisites-system-requirements-and-dependencies)** page before proceeding.

---

## 1. Understanding the Build Process

The OSBuild role automates the creation of custom Linux images using **image-builder** (for traditional ISO images) or **bootc** (for container-based images). The build process is divided into three phases:

1. **Infrastructure Setup**: Installs required packages and prepares the build environment.
2. **Repository Configuration**: Configures the necessary repositories for package sources.
3. **Blueprint Preparation and Build Execution**: Generates a blueprint (a declarative description of the image) and executes the build.

The role supports two primary build modes:
- **Traditional ISO**: Generates a bootable ISO image using `image-builder`.
- **Bootc Container Image**: Creates a container-based image for atomic updates.

By default, the role generates a build script (`build-<blueprint>.sh`) in the output directory. You can either run this script manually or configure the role to execute the build directly during the playbook run.

---

## 2. Configuring Your First Build

### Key Configuration Files

The OSBuild standalone repository and role use the following key files to define build configurations, package taxonomies, and playbooks:

| File / Path                  | Purpose                                                                                     | Location                     |
|------------------------------|---------------------------------------------------------------------------------------------|------------------------------|
| `osbuild.yml`                | Primary root playbook for composing custom images across supported distributions.          | `osbuild.yml`                |
| `playbooks/*.yml`            | Specialized appliance playbooks (e.g. `playbooks/osbuild-rocky-iso-nvidia.yml`).            | `playbooks/`                 |
| `inventory/hosts.yml`        | Builder host inventory targeting nodes (`gir`, `tinybot`) under `osbuild_targets`.          | `inventory/hosts.yml`        |
| `scripts/package_tracker.py` | Interactive TUI & CLI tool for inspecting taxonomy, managing packages, and build manifests.| `scripts/package_tracker.py` |
| `vars/packages/*.yml`        | Canonical package taxonomy YAML files (`00-distributions.yml`, `Fedora.yml`, `Rocky.yml`). | `vars/packages/`             |
| `roles/osbuild/defaults/main.yml` | Default role variables including distribution, architecture, and components.           | `roles/osbuild/defaults/main.yml` |
| `roles/osbuild/templates/blueprint.toml.j2` | Jinja2 template for generating the image blueprint.                        | `roles/osbuild/templates/blueprint.toml.j2` |

---

### Step 1: Define Your Build Variables

The `roles/osbuild/defaults/main.yml` file and the root playbook `osbuild.yml` contain the primary variables for configuring your build. Below are the key variables you can customize:

| Variable                     | Description                                                                                 | Default Value                     | Example Override                     |
|------------------------------|---------------------------------------------------------------------------------------------|-----------------------------------|---------------------------------------|
| `osbuild_distro`             | The target distribution and version for the build.                                         | Auto-detected (`fedora-43`, `rocky-10.2`) | `"rocky-10.2"`                       |
| `osbuild_arch`               | The target architecture for the build.                                                      | `"x86_64"`                        | `"aarch64"`                           |
| `osbuild_blueprint_name`     | The name of the blueprint (used for output files).                                          | `"workstation"`                   | `"my-workstation"`                    |
| `osbuild_components`         | The list of components to include in the build (e.g., `base`, `gnome`, `nvidia`).           | `["base", "anaconda", "gnome"]`   | `["base", "development", "nvidia"]`   |
| `osbuild_only_generate`      | If `true`, generates a build script without executing the build immediately.                | `true`                            | `false`                               |
| `osbuild_build_bootc`        | If `true`, builds a bootc container image instead of a traditional ISO.                     | `false`                           | `true`                                |
| `osbuild_output_dir`         | Directory where blueprints, build scripts, and finished images are saved.                   | `"/var/tmp/osbuild-images"`       | `"/var/lib/osbuild"`                  |

---

### Step 2: Inspect Packages and Select Components with Package Tracker

Before running a build, use the interactive **Package Tracker** tool (`scripts/package_tracker.py`) to explore distribution taxonomies, search package names, and assemble component sets.

#### Interactive TUI Mode

Launch the interactive terminal UI:

```bash
python3 scripts/package_tracker.py
# or explicitly
python3 scripts/package_tracker.py tui
```

The TUI provides several essential workflows:
- **📦 Select Packages & Create Build Manifest**: Interactively check off components and subcategories (`base`, `kernel`, `networking`, `desktop`, `audio`, `nvidia`, etc.) and export a build manifest (YAML, JSON, or TOML) into `build-selections/`.
- **🔍 Search Packages in Taxonomy**: Perform instant package lookups across Fedora, AlmaLinux, and Rocky Linux taxonomies to verify package naming and availability.
- **📋 List Taxonomy Categories & Counts**: Inspect available package categories and package counts for any target distribution.
- **➕ / ➖ Add or Remove Packages**: Update distribution YAML definitions in `vars/packages/` while preserving existing comments and formatting using `ruamel.yaml`.

#### CLI Non-Interactive Mode

For scripted environments or quick terminal inspections:

```bash
# Search for packages across distributions
python3 scripts/package_tracker.py search nvidia

# List categories and package counts for Rocky Linux
python3 scripts/package_tracker.py list --distro Rocky

# Generate a build manifest non-interactively
python3 scripts/package_tracker.py build \
  --distro Rocky \
  --blueprint workstation \
  --subcategories base,kernel,networking,gnome,nvidia \
  --format yaml
```

#### Component Definitions Summary

Components define the packages, services, and repositories bundled into your image. The `osbuild_components` variable determines which components are active:

| Component         | Description                                                                                 | Size Impact | Build Time Impact |
|-------------------|---------------------------------------------------------------------------------------------|-------------|-------------------|
| `base`            | Core system packages (kernel, systemd, NetworkManager).                                     | Small       | Low               |
| `anaconda`        | Anaconda installer (required for traditional ISO builds).                                   | Medium      | Medium            |
| `gnome`           | GNOME desktop environment.                                                                  | Large       | High              |
| `sway`            | Sway tiling window manager.                                                                 | Medium      | Medium            |
| `nvidia`          | NVIDIA proprietary driver and CUDA stack.                                                   | Large       | High              |
| `development`     | Development tools (GCC, Python, Node.js, Git).                                              | Large       | High              |
| `container-tools` | Container tools (Podman, Buildah, Skopeo).                                                  | Medium      | Medium            |
| `docker`          | Docker CE (experimental).                                                                    | Medium      | Medium            |

**Example: Customizing Components in Playbook Vars**
```yaml
osbuild_components:
  - base
  - anaconda
  - development
  - nvidia
```

Sources: [roles/osbuild/defaults/main.yml](roles/osbuild/defaults/main.yml#L80-L120), [scripts/package_tracker.py](scripts/package_tracker.py)

---

## 3. Running the Build

In the standalone `osbuild` repository, all playbooks and inventories are structured for immediate execution.

### Step 1: Select Your Playbook and Target Hosts

The repository includes pre-configured playbooks at the repo root and in `playbooks/`:
- `osbuild.yml`: Root playbook for custom workstation builds across Fedora, AlmaLinux, and Rocky Linux.
- `playbooks/osbuild-rocky-iso-nvidia.yml`: Verified Rocky Linux 10.2 Workstation ISO with pre-configured NVIDIA drivers and CUDA repositories.
- `playbooks/osbuild-rocky-cuda-container.yml`: Rocky Linux 10.2 CUDA application container appliance.
- `playbooks/osbuild-almalinux-iso.yml`: AlmaLinux 10.2 Workstation ISO installer.

Builder hosts are defined in `inventory/hosts.yml` under the `osbuild_targets` group (e.g. `gir` as local build host, `tinybot` via SSH). `ansible.cfg` automatically configures `inventory = ./inventory/hosts.yml` and `roles_path = ./roles`.

---

### Step 2: Execute the Playbook

Run the root playbook from the repository root:

```bash
ansible-playbook osbuild.yml
```

Or execute a dedicated variant playbook:

```bash
ansible-playbook playbooks/osbuild-rocky-iso-nvidia.yml
```

#### Controlling Build Execution

By default, `osbuild_only_generate: true` safely generates the blueprint TOML and the execution shell script (`build-<blueprint>.sh`) in the output directory (`/var/tmp/osbuild-images`) without triggering the time-consuming image compilation.

To execute the entire build directly through Ansible in a single run, set `osbuild_only_generate` to `false`:

```bash
ansible-playbook osbuild.yml -e osbuild_only_generate=false
```

To target a specific builder host:

```bash
ansible-playbook playbooks/osbuild-rocky-iso-nvidia.yml --limit gir
```

---

### Step 3: Run the Build Script (Optional)

If you ran with `osbuild_only_generate: true` (the default), navigate to the output directory and inspect or execute the generated build script:

```bash
cd /var/tmp/osbuild-images
sudo bash build-<blueprint>.sh
```

The script invokes `image-builder` directly with all resolved repositories, package lists, and blueprints.

---

### Step 4: Locate the Output

After the build finishes, image artifacts (bootable ISOs, container archives, or QCOW2 images) are located in the output directory (`osbuild_output_dir`). For example:

```
/var/tmp/osbuild-images/rocky-10-2-workstation-nvidia-rocky-10.2.x86_64.iso
```

---

## 4. Example: Build Configurations and Playbook Variants

### Root Workstation Playbook (`osbuild.yml`)

The root `osbuild.yml` playbook demonstrates dynamic distribution detection and modular component selection:

```yaml
---
- name: Build custom workstation image
  hosts: osbuild_targets
  become: true
  gather_facts: true

  vars:
    osbuild_distro_default:
      Fedora: "fedora-{{ ansible_distribution_major_version }}"
      AlmaLinux: "almalinux-{{ '9.8' if ansible_distribution_major_version == '9' else '10.2' }}"
      Rocky: "rocky-{{ '9.8' if ansible_distribution_major_version == '9' else '10.2' }}"
    osbuild_distro: "{{ osbuild_distro_default[ansible_distribution] }}"
    osbuild_arch: "x86_64"

    osbuild_blueprint_name: "workstation"
    osbuild_blueprint_version: "1.0.0"
    osbuild_blueprint_description: "Custom Workstation"

    osbuild_build_bootc: false
    osbuild_only_generate: true
    osbuild_output_dir: "/var/tmp/osbuild-images"

    osbuild_components:
      - base
      - anaconda
      - gnome
      - sway
      - nvidia
      - development
      - container-tools

  roles:
    - role: osbuild
```

### Pre-verified Variant Playbook (`playbooks/osbuild-rocky-iso-nvidia.yml`)

For specialized appliances such as Rocky Linux 10.2 with NVIDIA drivers, dedicated playbooks pin verified blueprints and repositories:

```yaml
---
- name: Build Rocky Linux 10.2 workstation ISO installer (NVIDIA)
  hosts: builder
  become: true
  gather_facts: false
  vars:
    osbuild_distro: "rocky-10.2"
    osbuild_arch: "x86_64"
    osbuild_blueprint_name: "rocky-10-2-workstation-nvidia"
    osbuild_use_blueprint_template: false
    osbuild_static_blueprint_path: "files/rocky/10/x86_64/workstation/rocky-10-2-workstation-nvidia.toml"
    osbuild_only_generate: true
    osbuild_output_dir: "/var/tmp/osbuild-images"

  roles:
    - role: osbuild
```

### Expected Output
- Blueprint file: `/var/tmp/osbuild-images/<blueprint-name>.toml`
- Build script: `/var/tmp/osbuild-images/build-<blueprint-name>.sh`
- Bootable ISO image: `/var/tmp/osbuild-images/<blueprint-name>-<distro>.<arch>.iso` (when executed)

---

## 5. Next Steps

Now that you have successfully set up and run your first build, consider exploring the following topics to deepen your understanding:

1. **[Prerequisites: System Requirements and Dependencies](3-prerequisites-system-requirements-and-dependencies)**: Learn about the hardware and software requirements for running the OSBuild role.
2. **[Understanding Blueprints: Definition and Customization](6-understanding-blueprints-definition-and-customization)**: Dive deeper into blueprints and how to customize them for your use case.
3. **[Build Modes: Selecting and Configuring for Your Use Case](8-build-modes-selecting-and-configuring-for-your-use-case)**: Explore the different build modes (traditional ISO vs. bootc) and how to configure them.
4. **[Kickstart Files: Automation and Configuration](7-kickstart-files-automation-and-configuration)**: Learn how to automate the installation process using kickstart files.

---

## 6. Troubleshooting

### Common Issues and Solutions

| Issue                                      | Possible Cause                                                                 | Solution                                                                                     |
|--------------------------------------------|---------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| Playbook fails with "unsupported distribution" | The build host is not Fedora, AlmaLinux, or Rocky Linux.                        | Verify your build host meets the system requirements.                                        |
| Build script fails with "command not found" | `image-builder` or other dependencies are not installed.                        | Run the playbook again to ensure all dependencies are installed.                             |
| Blueprint validation fails                 | Invalid component selection or missing dependencies.                            | Check the `osbuild_components` list for conflicts or missing dependencies.                  |
| Insufficient disk space                    | The build host does not have enough disk space for the build.                   | Free up disk space or configure a different output directory using `osbuild_output_dir`.     |

Sources: [tasks/main.yml](tasks/main.yml#L20-L60), [tasks/install.yml](tasks/install.yml#L1-L20)

---