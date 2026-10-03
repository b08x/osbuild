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

The OSBuild role uses the following key files to define the build configuration:

| File                     | Purpose                                                                                     | Location                     |
|--------------------------|---------------------------------------------------------------------------------------------|------------------------------|
| `defaults/main.yml`      | Default variables for the build, including distribution, architecture, and components.      | `defaults/main.yml`          |
| `vars/<Distribution>.yml`| Distribution-specific repository and package configurations.                               | `vars/Fedora.yml`            |
| `tasks/main.yml`         | Orchestrates the build process, including mode selection and task execution.                | `tasks/main.yml`             |
| `templates/blueprint.toml.j2` | Jinja2 template for generating the blueprint file, which defines the image composition. | `templates/blueprint.toml.j2`|

---

### Step 1: Define Your Build Variables

The `defaults/main.yml` file contains the primary variables for configuring your build. Below are the key variables you need to customize for your first build:

| Variable                     | Description                                                                                 | Default Value                     | Example Override                     |
|------------------------------|---------------------------------------------------------------------------------------------|-----------------------------------|---------------------------------------|
| `osbuild_distro`             | The target distribution and version for the build.                                         | `"fedora-43"`                     | `"almalinux-10.2"`                   |
| `osbuild_arch`               | The target architecture for the build.                                                      | `"x86_64"`                        | `"aarch64"`                           |
| `osbuild_blueprint_name`     | The name of the blueprint (used for output files).                                          | `"custom"`                        | `"my-workstation"`                    |
| `osbuild_components`         | The list of components to include in the build (e.g., `base`, `gnome`, `nvidia`).           | `["base", "anaconda", "gnome"]`   | `["base", "development", "docker"]`   |
| `osbuild_only_generate`      | If `true`, generates a build script without executing the build.                            | `true`                            | `false`                               |
| `osbuild_build_bootc`        | If `true`, builds a bootc container image instead of a traditional ISO.                     | `false`                           | `true`                                |

For your first build, we recommend using the default values for `osbuild_distro` and `osbuild_arch`, and customizing only the `osbuild_blueprint_name` and `osbuild_components`.

---

### Step 2: Customize the Components

Components define the packages, services, and repositories included in your image. The `osbuild_components` variable in `defaults/main.yml` determines which components are included. Below is a summary of the available components:

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

For your first build, start with the `base` and `anaconda` components. You can add more components as needed.

**Example: Customizing Components**
```yaml
osbuild_components:
  - base
  - anaconda
  - development
```

Sources: [defaults/main.yml](defaults/main.yml#L80-L120)

---

## 3. Running the Build

### Step 1: Create a Playbook

Create an Ansible playbook to execute the OSBuild role. Below is a minimal example:

```yaml
---
- name: Run OSBuild Role
  hosts: localhost
  become: true
  roles:
    - osbuild
```

Save this playbook as `osbuild.yml` in your working directory.

---

### Step 2: Execute the Playbook

Run the playbook using the following command:

```bash
ansible-playbook osbuild.yml
```

By default, this will generate a build script (`build-<blueprint>.sh`) in the output directory (`/var/lib/osbuild` by default). The script contains the commands required to execute the build using `image-builder`.

---

### Step 3: Run the Build Script (Optional)

If you set `osbuild_only_generate: true` (the default), navigate to the output directory and run the build script:

```bash
cd /var/lib/osbuild
sudo bash build-<blueprint>.sh
```

If you set `osbuild_only_generate: false`, the build will execute automatically during the playbook run.

---

### Step 4: Locate the Output

After the build completes, the output files (e.g., ISO image or container image) will be available in the output directory. For traditional ISO builds, the output file will be named `<blueprint-name>-<distro>-<arch>.<image-type>`. For example:

```
/var/lib/osbuild/my-workstation-fedora-43.x86_64.iso
```

---

## 4. Example: Minimal Build Configuration

Below is an example of a minimal build configuration for a Fedora 43 workstation with the GNOME desktop environment.

### Playbook (`osbuild.yml`)
```yaml
---
- name: Run OSBuild Role
  hosts: localhost
  become: true
  vars:
    osbuild_blueprint_name: "my-workstation"
    osbuild_components:
      - base
      - anaconda
      - gnome
  roles:
    - osbuild
```

### Expected Output
- A blueprint file: `/var/lib/osbuild/my-workstation.toml`
- A build script: `/var/lib/osbuild/build-my-workstation.sh`
- A bootable ISO image: `/var/lib/osbuild/my-workstation-fedora-43.x86_64.iso` (if `osbuild_only_generate: false`)

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