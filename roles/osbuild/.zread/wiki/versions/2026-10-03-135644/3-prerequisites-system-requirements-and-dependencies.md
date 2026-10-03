This document outlines the **mandatory** and **recommended** prerequisites for setting up a build host to run the OSBuild role. It covers **operating system compatibility**, **software dependencies**, **resource requirements**, and **build mode-specific constraints**.

Understanding these prerequisites ensures a smooth setup process and avoids common pitfalls during image generation. After reviewing this page, you will be prepared to configure your build environment and proceed to **[Repository Structure and Key Files Explained](4-repository-structure-and-key-files-explained)**.

---

## 1. Operating System Requirements

The OSBuild role is designed exclusively for **Red Hat-family Linux distributions**. It has been tested and validated on the following platforms:

| Distribution       | Supported Versions                     | Notes                                  |
|--------------------|----------------------------------------|----------------------------------------|
| **Fedora**         | 43 (latest tested)                     | Primary development platform           |
| **AlmaLinux**      | 8, 9, 10 (latest tested: 10.2)         | EL-family compatibility                |
| **Rocky Linux**    | 9, 10 (latest tested: 10.2)            | EL-family compatibility                |

### Validation
The role enforces this requirement at runtime using an `ansible.builtin.assert` task. If the host OS is unsupported, the playbook fails immediately with a descriptive error message.
**Sources**: [`tasks/main.yml`](tasks/main.yml#L28-L36)

---

## 2. Software Dependencies

### Core Dependencies
The following packages and tools **must** be installed on the build host:

| Dependency               | Purpose                                                                 | Installation Method                     |
|--------------------------|-------------------------------------------------------------------------|-----------------------------------------|
| **Ansible**              | Automation engine for running the role                                  | `dnf install ansible-core` (or `pip`)   |
| **image-builder-cli**    | CLI tool for building disk images and ISOs                              | Installed automatically by the role     |
| **osbuild-composer**     | Backend service for composing custom images                             | Installed automatically by the role     |
| **podman**               | Container runtime for `bootc` image builds (if `osbuild_build_bootc=true`) | Installed automatically by the role     |
| **firewalld** (optional) | Network security for build services                                     | Installed automatically if available    |

### Distribution-Specific Packages
The role dynamically installs the required packages based on the host distribution. The package lists are defined in:
- [`vars/Fedora.yml`](vars/Fedora.yml)
- [`vars/AlmaLinux.yml`](vars/AlmaLinux.yml)
- [`vars/Rocky.yml`](vars/Rocky.yml)

**Example**: For Fedora, the following packages are installed:
```yaml
osbuild_host_packages:
  - osbuild-composer
  - composer-cli
  - podman
  - buildah
  - skopeo
  - jq
  - firewalld
```
**Sources**: [`tasks/install.yml`](tasks/install.yml#L14-L18), [`vars/Fedora.yml`](vars/Fedora.yml#L1-L20)

---

## 3. Resource Requirements

### Disk Space
The build process requires **significant temporary and output storage**. The role enforces a **minimum of 50GB of free disk space** in the directory containing `osbuild_work_dir` (default: `/var/lib/osbuild-composer`).

| Requirement               | Value                     | Notes                                  |
|---------------------------|---------------------------|----------------------------------------|
| **Minimum Free Space**    | 50GB                      | Validated at runtime                   |
| **Recommended Free Space**| 100GB+                    | For large builds (e.g., `oneapi`)      |
| **Output Directory**      | `osbuild_output_dir`      | Default: `./output` (relative to playbook) |

**Validation**: The role checks disk space at runtime using a shell command. If the requirement is not met, the playbook fails with a clear error message.
**Sources**: [`tasks/install.yml`](tasks/install.yml#L4-L12)

### Memory and CPU
While the role does not enforce strict memory or CPU requirements, the following recommendations apply:

| Resource       | Recommendation                     | Notes                                  |
|----------------|------------------------------------|----------------------------------------|
| **RAM**        | 8GB+ (16GB+ for `oneapi` builds)   | Insufficient memory may cause OOM kills |
| **CPU Cores**  | 4+                                 | Builds are CPU-intensive               |

---

## 4. Build Mode-Specific Requirements

The OSBuild role supports **three build modes**, each with slightly different prerequisites:

| Build Mode               | Description                                                                 | Additional Requirements                                                                 |
|--------------------------|-----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| **Traditional ISO**      | Generates a bootable ISO image (default)                                    | None                                                                                     |
| **Bootc Container Image**| Generates a bootable container image for atomic updates (`osbuild_build_bootc=true`) | `podman` installed and configured                                                        |
| **Generate Only**        | Generates blueprint and build script without executing the build (`osbuild_only_generate=true`) | None                                                                                     |

**Sources**: [`tasks/select_build_mode.yml`](tasks/select_build_mode.yml) (hypothetical, inferred from `tasks/main.yml`), [`defaults/main.yml`](defaults/main.yml#L25-L35)

---

## 5. Network Requirements

The build process requires **internet access** to fetch:
- OS packages from distribution repositories
- GPG keys for repository validation
- Container images (if using `bootc` mode)
- Proprietary drivers (e.g., NVIDIA CUDA, if the `nvidia` component is selected)

### Firewall Configuration
If `firewalld` is installed, the role ensures it is running. However, no specific ports are opened by default. If you encounter connectivity issues, ensure the following domains are accessible:
- `*.fedoraproject.org`
- `*.rpmfusion.org`
- `developer.download.nvidia.com`
- `nvidia.github.io`
- `registry.fedoraproject.org` (for `bootc` builds)

**Sources**: [`tasks/install.yml`](tasks/install.yml#L25-L32)

---

## 6. Ansible Requirements

### Ansible Version
The role requires **Ansible 2.15 or later**. This is enforced in the role metadata.

| Requirement       | Value                     | Notes                                  |
|-------------------|---------------------------|----------------------------------------|
| **Minimum Version** | 2.15                     | Validated in `meta/main.yml`           |
| **Python Version**  | 3.9+                     | Required by Ansible                    |

**Sources**: [`meta/main.yml`](meta/main.yml#L7)

### Collections and Roles
The OSBuild role has **no external Ansible collection dependencies**. However, it relies on a **collection-level package taxonomy** defined in:
- [`vars/packages/Fedora.yml`](vars/packages/Fedora.yml)
- [`vars/packages/AlmaLinux.yml`](vars/packages/AlmaLinux.yml)
- [`vars/packages/Rocky.yml`](vars/packages/Rocky.yml)

This creates a **soft dependency** on the collection structure. The role cannot be used standalone without these files.
**Sources**: [`tasks/main.yml`](tasks/main.yml#L51-L53), [`vars/packages.yml`](vars/packages.yml#L1-L11)

---

## 7. User Permissions

The role **must** be executed with **root privileges** (or via `sudo`). This is required to:
- Install system packages
- Create directories in `/var/lib/osbuild-composer`
- Start and enable system services (e.g., `osbuild-composer.socket`)

---

## 8. Next Steps

After ensuring your build host meets these prerequisites, proceed to:
1. **[Repository Structure and Key Files Explained](4-repository-structure-and-key-files-explained)**: Understand the role's directory layout and key files.
2. **[Default Variables and Overrides in `defaults/main.yml`](9-default-variables-and-overrides-in-defaults-main-yml)**: Learn how to customize the build process.
3. **[Quick Start: Setting Up and Running Your First Build](2-quick-start-setting-up-and-running-your-first-build)**: Execute your first build.

**Sources**: [`README.md`](README.md#L1-L20), [Catalog Structure](#navigation-context)