This page explains how the OSBuild role configures **disk images** (e.g., QCOW2, RAW) and **ISO installers** for Linux distributions. The role uses **TOML-based templates** to define filesystem layouts, installer settings, and boot configurations, which are dynamically resolved based on the selected **build mode** (`traditional_iso`, `bootc_image`, or `generate_only`).

---

## **1. Build Mode Selection**
The role supports **three build modes**, resolved in `tasks/select_build_mode.yml`:

| Mode               | Description                                                                                     | Trigger Variables                                                                 |
|--------------------|-------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| `bootc_image`      | Builds a **bootc container image** for atomic OS updates.                                      | `osbuild_build_bootc: true`                                                       |
| `traditional_iso`  | Builds a **traditional ISO installer** (e.g., `image-installer` or `minimal-installer`).       | `osbuild_build_bootc: false`, `osbuild_only_generate: false`                      |
| `generate_only`    | Generates a **build script** without executing it (default for traditional ISOs).              | `osbuild_build_bootc: false`, `osbuild_only_generate: true` (default)             |

The resolved mode (`osbuild_resolved_build_mode`) determines which **templates and tasks** are executed during the build process.
**Sources**: [tasks/select_build_mode.yml](tasks/select_build_mode.yml#L1-L33)

---

## **2. Disk Image Configuration**
Disk images (e.g., QCOW2, RAW) are configured using the `disk.toml.j2` template. This template defines **filesystem layouts, mount points, and minimum sizes** for the target image.

### **Key Configuration Options**
| Option                     | Description                                                                                     | Default Value                     | Example Override                          |
|----------------------------|-------------------------------------------------------------------------------------------------|-----------------------------------|-------------------------------------------|
| `osbuild_bootc_root_size`  | Minimum size of the root (`/`) filesystem.                                                      | `20 GiB`                          | `osbuild_bootc_root_size: "50 GiB"`       |
| `osbuild_bootc_home_size`  | Minimum size of the `/home` filesystem (optional).                                              | `undefined`                       | `osbuild_bootc_home_size: "100 GiB"`      |
| `osbuild_bootc_var_size`   | **Not supported** by `bootc-image-builder` (commented out in template).                          | `undefined`                       | N/A                                       |

### **Example: `disk.toml.j2`**
```toml
# {{ ansible_managed }}
# Disk configuration for bootc QCOW2/RAW image builds
# Used by bootc-image-builder for {{ osbuild_blueprint_name }}

[[customizations.filesystem]]
mountpoint = "/"
minsize = "{{ osbuild_bootc_root_size | default('20 GiB') }}"

{% if osbuild_bootc_home_size is defined %}
[[customizations.filesystem]]
mountpoint = "/home"
minsize = "{{ osbuild_bootc_home_size }}"
{% endif %}
```
**Sources**: [templates/disk.toml.j2](templates/disk.toml.j2#L1-L27)

---

## **3. ISO Configuration**
ISO installers are configured using the `iso.toml.j2` template. This template defines **Anaconda installer modules, kickstart integration, and bootloader settings**.

### **Key Configuration Options**
| Option                     | Description                                                                                     | Default Value                     | Example Override                          |
|----------------------------|-------------------------------------------------------------------------------------------------|-----------------------------------|-------------------------------------------|
| `customizations.installer.kickstart.contents` | Kickstart file contents embedded in the ISO.                                                    | Empty (placeholder)               | Custom kickstart content                  |
| `customizations.installer.modules.enable`     | Anaconda modules enabled during installation.                                                   | Required Fedora modules           | Add/remove modules as needed              |
| `customizations.installer.modules.disable`    | Anaconda modules disabled during installation.                                                  | `Subscription` module             | Add/remove modules as needed              |

### **Example: `iso.toml.j2`**
```toml
# {{ ansible_managed }}
# ISO configuration for bootc installer builds
# Used by bootc-image-builder for {{ osbuild_blueprint_name }}

[customizations.installer.kickstart]
contents = """
# Kickstart for bootc installer
# The installer payload is embedded in the ISO and handled by bootc-image-builder
"""

[customizations.installer.modules]
enable = [
  "org.fedoraproject.Anaconda.Modules.Storage",
  "org.fedoraproject.Anaconda.Modules.Runtime",
  "org.fedoraproject.Anaconda.Modules.Network"
]
disable = [
  "org.fedoraproject.Anaconda.Modules.Subscription"
]
```
**Sources**: [templates/iso.toml.j2](templates/iso.toml.j2#L1-L32)

---

## **4. Build Execution**
The build process is executed in `tasks/build.yml` and varies based on the resolved build mode:

### **Traditional ISO Build**
1. **Generate Build Script**: If `osbuild_only_generate: true`, the role generates a script (`build-{{ osbuild_blueprint_name }}.sh`) in the output directory.
2. **Execute Build**: The script runs `image-builder` with the resolved configuration (e.g., `--distro`, `--blueprint`, `--extra-repo`).
3. **Output Handling**: The newest image (e.g., `.iso`, `.qcow2`) is copied to the specified output filename.

### **Bootc Image Build**
1. **Repository Bootstrap**: Third-party repositories (e.g., RPMFusion, NVIDIA CUDA) are installed before package installation.
2. **Build Execution**: The `image-builder` command is executed with the `bootc` configuration.
3. **Container Loading**: If the output is a container image, it is loaded into Podman and tagged.

### **Example: Build Command**
```bash
image-builder build {{ osbuild_image_type }} \
  --distro {{ osbuild_distro }} \
  --blueprint {{ osbuild_blueprint_name }}.toml \
  --extra-repo "https://developer.download.nvidia.com/compute/cuda/repos/fedora43/x86_64"
```
**Sources**: [tasks/build.yml](tasks/build.yml#L1-L139), [templates/image-builder-build.sh.j2](templates/image-builder-build.sh.j2#L1-L40)

---

## **5. Default Variables and Overrides**
The `defaults/main.yml` file defines **default variables** for disk image and ISO configuration. Key variables include:

| Variable                     | Description                                                                                     | Default Value                     |
|------------------------------|-------------------------------------------------------------------------------------------------|-----------------------------------|
| `osbuild_distro`             | Target distribution (e.g., `fedora-43`, `almalinux-10`).                                        | `fedora-43`                       |
| `osbuild_image_type`         | Output format (e.g., `qcow2`, `image-installer`, `minimal-installer`).                          | `minimal-installer` (Fedora)      |
| `osbuild_bootc_root_size`    | Minimum root filesystem size for `bootc` images.                                                | `20 GiB`                          |
| `osbuild_extra_repo_urls`    | Additional repositories for package installation.                                               | `[]`                              |

**Sources**: [defaults/main.yml](defaults/main.yml#L1-L100)

---

## **6. Next Steps**
1. **[Default Variables and Overrides](9-default-variables-and-overrides-in-defaults-main-yml)**: Learn how to customize build configurations.
2. **[Build Modes: Selecting and Configuring for Your Use Case](8-build-modes-selecting-and-configuring-for-your-use-case)**: Explore advanced build mode options.
3. **[Handling Post-Installation Tasks with Systemd Services](16-handling-post-installation-tasks-with-systemd-services)**: Configure post-installation tasks for your images.