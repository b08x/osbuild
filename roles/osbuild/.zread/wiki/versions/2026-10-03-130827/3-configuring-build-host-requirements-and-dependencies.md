This guide outlines the **prerequisites**, **host configuration**, and **dependency management** required to prepare a build host for the OSBuild role. It focuses on the **infrastructure setup** phase, ensuring the environment meets the technical and resource requirements for image generation.

---

## Supported Build Hosts and Operating Systems

The OSBuild role **exclusively supports** Red Hat-compatible distributions as build hosts. This ensures compatibility with the `image-builder` CLI and underlying tooling.

| **Distribution** | **Supported Versions** | **Architectures**       |
|------------------|------------------------|-------------------------|
| Fedora           | 43                     | x86_64, aarch64         |
| AlmaLinux        | 8, 9, 10               | x86_64, aarch64         |
| Rocky Linux      | 9, 10                  | x86_64, aarch64         |

**Validation**: The role enforces this requirement via an `ansible.builtin.assert` task in [`tasks/main.yml`](tasks/main.yml#L28-L36), failing fast if the host OS is unsupported.

Sources: [tasks/main.yml](tasks/main.yml#L28-L36)

---

## Minimum System Requirements

### Disk Space
The build host **must** have at least **50GB of free disk space** in the directory containing `osbuild_work_dir` (default: `/var/lib/osbuild-composer`). This requirement is validated at runtime via a shell command in [`tasks/install.yml`](tasks/install.yml#L4-L12).

| **Requirement**       | **Default Value** | **Purpose**                          |
|-----------------------|-------------------|--------------------------------------|
| Minimum Disk Space    | 50GB              | Accommodates large images (e.g., oneAPI adds ~15GB) |
| Work Directory        | `/var/lib/osbuild-composer` | Temporary build artifacts and caches |
| Output Directory      | `/var/tmp/osbuild-images`   | Final ISO/container images          |
| Log Directory         | `/var/tmp/osbuild-logs`     | Build logs and debug output         |

**Validation Logic**:
```yaml
- name: Check minimum disk space requirement
  ansible.builtin.shell: |
    df -BG {{ osbuild_work_dir | dirname }} | awk 'NR==2 {print $4}' | sed 's/G//'
  register: available_space
  failed_when: available_space.stdout | int < osbuild_min_disk_space
```
Sources: [tasks/install.yml](tasks/install.yml#L4-L12), [defaults/main.yml](defaults/main.yml#L794)

---

## Required Packages on the Build Host

The OSBuild role dynamically installs **host-specific packages** based on the detected distribution. These packages are defined in [`defaults/main.yml`](defaults/main.yml#L638-L658) under `osbuild_host_packages`.

### Package List by Distribution

| **Distribution** | **Packages**                                                                                     |
|------------------|-------------------------------------------------------------------------------------------------|
| **Fedora**       | `osbuild`, `image-builder`, `bash-completion`, `firewalld`, `openscap-scanner`, `scap-security-guide`, `python3-tomli` |
| **AlmaLinux**    | `osbuild`, `image-builder`, `bash-completion`, `firewalld`, `openscap-scanner`, `scap-security-guide`, `python3-tomli` |
| **Rocky Linux**  | `osbuild`, `image-builder`, `bash-completion`, `firewalld`, `openscap-scanner`, `scap-security-guide`, `python3-tomli` |

**Installation Task**:
```yaml
- name: Install image-builder and related packages
  ansible.builtin.dnf:
    name: "{{ osbuild_host_packages[ansible_distribution] }}"
    state: present
  become: true
```
Sources: [tasks/install.yml](tasks/install.yml#L14-L18), [defaults/main.yml](defaults/main.yml#L638-L658)

---

## Directory Structure and Permissions

The role creates and configures the following directories during the **Phase 1: Infrastructure Setup** (see [`tasks/main.yml`](tasks/main.yml#L60-L68)):

| **Directory**               | **Purpose**                              | **Default Permissions** |
|-----------------------------|------------------------------------------|-------------------------|
| `osbuild_output_dir`        | Stores generated blueprints and scripts | `0755`                  |
| `osbuild_log_dir`           | Build logs and debug output              | `0755`                  |
| `osbuild_work_dir`          | Temporary build artifacts                | System default          |
| `osbuild_gpgkey_cache_dir`  | Cached GPG keys for repositories         | Inherited from `osbuild_work_dir` |

**Directory Creation Task**:
```yaml
- name: Create output directories
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    mode: "0755"
  loop:
    - "{{ osbuild_output_dir }}"
    - "{{ osbuild_log_dir }}"
```
Sources: [tasks/install.yml](tasks/install.yml#L20-L26), [defaults/main.yml](defaults/main.yml#L733-L788)

---

## Optional Dependencies

### Firewalld
The role **optionally** enables and starts `firewalld` if it is present on the build host. This is handled gracefully with a `block`/`rescue` pattern to avoid failures on systems without `firewalld`:

```yaml
- name: Enable firewalld (optional)
  block:
    - name: Ensure firewalld is running
      ansible.builtin.systemd:
        name: firewalld
        state: started
        enabled: true
      become: true
  rescue:
    - name: Report firewalld unavailable
      ansible.builtin.debug:
        msg: "firewalld is not present or could not be started; skipping (optional dependency)."
```
Sources: [tasks/install.yml](tasks/install.yml#L28-L38)

---

## Build Mode Considerations

The OSBuild role supports **three build modes**, resolved in [`tasks/select_build_mode.yml`](tasks/select_build_mode.yml#L1-L33). The **host requirements** vary slightly depending on the mode:

| **Build Mode**          | **Description**                                                                 | **Host Requirements**                                                                 |
|-------------------------|---------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| `traditional_iso`       | Builds a traditional ISO image using `image-builder` CLI.                      | Full `image-builder` toolchain, sufficient disk space for ISO artifacts.               |
| `bootc_image`           | Builds a **bootc-compatible container image** for atomic updates.               | `image-builder` + container runtime (e.g., Podman), additional space for container layers. |
| `generate_only`         | Generates blueprint and build script **without executing the build**.           | Minimal: Only requires `image-builder` CLI for blueprint validation.                 |

**Mode Resolution Logic**:
```yaml
osbuild_resolved_build_mode: >-
  {{
    osbuild_build_bootc
    | ternary('bootc_image',
      osbuild_only_generate
      | ternary('generate_only', 'traditional_iso')
    )
  }}
```
Sources: [tasks/select_build_mode.yml](tasks/select_build_mode.yml#L1-L33)

---

## Distribution-Specific Repository Configuration

The OSBuild role **dynamically loads** distribution-specific repository configurations from:
- [`vars/Fedora.yml`](vars/Fedora.yml) for Fedora
- [`vars/AlmaLinux.yml`](vars/AlmaLinux.yml) for AlmaLinux
- [`vars/Rocky.yml`](vars/Rocky.yml) for Rocky Linux

These files define **base repositories** (e.g., `fedora`, `updates`, `rpmfusion-free`) and **GPG key URLs** (preferring `file://` paths to `/usr/share/distribution-gpg-keys/` when available).

**Example: Fedora Repository Configuration**
```yaml
repo:
  fedora:
    metalink: "https://mirrors.fedoraproject.org/metalink?repo=fedora-43&arch=x86_64"
    gpgkey_url: "file:///usr/share/distribution-gpg-keys/fedora/RPM-GPG-KEY-fedora-43-primary"
    check_gpg: true
  rpmfusion-free:
    baseurl: "http://download1.rpmfusion.org/free/fedora/releases/43/Everything/x86_64/os/"
    gpgkey_url: "file:///usr/share/distribution-gpg-keys/rpmfusion/RPM-GPG-KEY-rpmfusion-free-fedora-43"
    check_gpg: true
```
Sources: [vars/Fedora.yml](vars/Fedora.yml#L1-L79), [vars/AlmaLinux.yml](vars/AlmaLinux.yml#L1-L68), [vars/Rocky.yml](vars/Rocky.yml#L1-L90)

---

## Component-Driven Dependency Management

The OSBuild role uses a **modular component system** to manage dependencies. Each component (e.g., `nvidia`, `development`, `container-tools`) defines its own **packages**, **sources**, and **requirements**.

### Key Components and Their Dependencies

| **Component**       | **Purpose**                          | **Key Dependencies**                                                                 | **Size Impact** | **Build Time Impact** |
|---------------------|--------------------------------------|------------------------------------------------------------------------------------|-----------------|------------------------|
| `base`              | Core system (kernel, systemd, etc.)  | `system_packages.System.kernel`, `system_packages.System.base`                     | Small           | None                   |
| `nvidia`            | NVIDIA GPU stack                     | `system_packages.Graphics.nvidia`, `_nvidia_sources` (CUDA, RPM Fusion)           | Large           | Medium                 |
| `development`       | Development tools                    | GCC, Python, Node.js, CMake, Git                                                   | Medium          | Medium                 |
| `container-tools`   | Container runtime tools              | Podman, Buildah, Skopeo, Docker CE                                                | Small           | Low                    |
| `oneapi`            | Intel oneAPI                         | BaseKit + HPCKit                                                                   | Large           | High                   |

**Component Definition Example (NVIDIA)**:
```yaml
nvidia:
  label: "NVIDIA GPU Stack"
  packages: "{{ system_packages.Graphics.nvidia }}"
  sources: "{{ _nvidia_sources }}"
  bootc_repos: "{{ _nvidia_bootc_repos }}"
  requires:
    - base
  size_impact: "large"
  build_time_impact: "medium"
  secure_boot_compatible: false
```
Sources: [defaults/main.yml](defaults/main.yml#L240-L260)

---

## Mermaid Diagram: Build Host Setup Workflow

```mermaid
flowchart TD
    A[Start OSBuild Role] --> B[Validate OS Compatibility]
    B -->|Fedora/AlmaLinux/Rocky| C[Load Distribution-Specific Vars]
    B -->|Unsupported OS| D[Fail Fast]
    C --> E[Load Package Taxonomy]
    E --> F[Resolve Build Mode]
    F --> G[Phase 1: Infrastructure Setup]
    G --> H[Check Disk Space]
    H -->|Sufficient| I[Install Host Packages]
    H -->|Insufficient| J[Fail with Error]
    I --> K[Create Output Directories]
    K --> L[Enable firewalld (Optional)]
    L --> M[Phase 2: Repository Configuration]
    M --> N[Fetch GPG Keys]
    N --> O[Configure Sources]
    O --> P[Proceed to Build Mode Tasks]
```

---

## Next Steps

After configuring the build host requirements and dependencies, proceed to:
- **[Selecting Target Distribution and Architecture](4-selecting-target-distribution-and-architecture)** to define the image output.
- **[Understanding Traditional ISO vs. Bootc Container Build Modes](5-understanding-traditional-iso-vs-bootc-container-build-modes)** to choose the appropriate build method.