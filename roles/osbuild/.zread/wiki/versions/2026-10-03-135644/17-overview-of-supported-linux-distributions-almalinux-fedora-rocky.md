This page provides a **beginner-friendly overview** of the Linux distributions supported by the **OSBuild role**: **AlmaLinux**, **Fedora**, and **Rocky Linux**. It explains how each distribution is integrated into the build system, their key differences, and how the role adapts to their unique requirements. This document is designed to help developers understand the **distribution-specific configurations**, **repository strategies**, and **build compatibility** without requiring deep prior knowledge of OSBuild or Ansible.

If you are new to this role, we recommend starting with:
- **[Overview: Purpose and Value of the OSBuild Role](1-overview-purpose-and-value-of-the-osbuild-role)** for context on why this role exists.
- **[Quick Start: Setting Up and Running Your First Build](2-quick-start-setting-up-and-running-your-first-build)** to see the role in action.

---

## **1. Supported Distributions at a Glance**
The OSBuild role supports three major Linux distributions, each targeting different use cases:

| Distribution  | Primary Use Case                          | Key Characteristics                                                                 | Default Build Mode                     | Compatible Architectures |
|---------------|-------------------------------------------|------------------------------------------------------------------------------------|----------------------------------------|--------------------------|
| **Fedora**    | Cutting-edge development, desktop/workstation | Rapid release cycle (6 months), latest software, upstream for RHEL                | `minimal-installer` (ISO)              | `x86_64`, `aarch64`      |
| **AlmaLinux** | Enterprise stability, server/workstation  | RHEL-compatible, long-term support (10 years), binary-compatible with RHEL        | `image-installer` (ISO)                | `x86_64`, `aarch64`      |
| **Rocky Linux** | Enterprise stability, server/workstation  | RHEL-compatible, community-driven, binary-compatible with RHEL                    | `image-installer` (ISO)                | `x86_64`, `aarch64`      |

**Key Takeaway**:
Fedora is ideal for **developers** who need the latest features, while AlmaLinux and Rocky Linux are better suited for **stable, long-term deployments** in enterprise or production environments.
*Sources: [defaults/main.yml](defaults/main.yml#L14-L44), [meta/main.yml](meta/main.yml#L8-L20)*

---

## **2. How the Role Adapts to Each Distribution**
The OSBuild role uses **distribution-specific variables** and **conditional logic** to ensure compatibility with each supported distribution. This section explains the **core mechanisms** that enable this adaptability.

### **2.1. Distribution Detection and Variable Loading**
The role automatically detects the **build host's distribution** (Fedora, AlmaLinux, or Rocky Linux) and loads the corresponding variables from:
- `vars/Fedora.yml`
- `vars/AlmaLinux.yml`
- `vars/Rocky.yml`

This ensures that **repository configurations**, **GPG keys**, and **package sources** are tailored to the selected distribution.

**Example**:
When building on **Fedora 43**, the role loads `vars/Fedora.yml` and configures repositories like `fedora`, `updates`, and `rpmfusion-free`.
*Sources: [tasks/main.yml](tasks/main.yml#L55-L57), [vars/Fedora.yml](vars/Fedora.yml#L19-L78)*

## **2.2. Repository Configuration**
Each distribution has a **unique repository ecosystem**, and the role handles these differences transparently.

### **Fedora**
- Uses **Fedora's official repositories** (`fedora`, `updates`) and **RPM Fusion** for proprietary drivers (e.g., NVIDIA).
- **NVIDIA CUDA** repositories are configured with Fedora-specific paths (e.g., `fedora43`).
- **Example Repositories**:
  - `fedora`: [https://mirrors.fedoraproject.org/metalink?repo=fedora-43&arch=x86_64](https://mirrors.fedoraproject.org/metalink?repo=fedora-43&arch=x86_64)
  - `rpmfusion-free`: [http://download1.rpmfusion.org/free/fedora/releases/43/Everything/x86_64/os/](http://download1.rpmfusion.org/free/fedora/releases/43/Everything/x86_64/os/)
  - `nvidia-container-toolkit`: [https://nvidia.github.io/libnvidia-container/stable/rpm/x86_64](https://nvidia.github.io/libnvidia-container/stable/rpm/x86_64)

*Sources: [vars/Fedora.yml](vars/Fedora.yml#L19-L78)*

### **AlmaLinux**
- Uses **AlmaLinux's official repositories** (`baseos`, `appstream`, `crb`) and **EPEL** for additional packages.
- **RPM Fusion** is used for proprietary drivers, but only the `updates` channel is available (no `releases` channel).
- **NVIDIA CUDA** repositories use RHEL-compatible paths (e.g., `rhel10`).
- **Example Repositories**:
  - `almalinux-baseos`: [https://mirrors.almalinux.org/metalink?repo=baseos-10.2&arch=x86_64](https://mirrors.almalinux.org/metalink?repo=baseos-10.2&arch=x86_64)
  - `epel`: [https://mirror.us.leaseweb.net/epel/10/Everything/x86_64/](https://mirror.us.leaseweb.net/epel/10/Everything/x86_64/)
  - `cuda-el10-x86_64`: [https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64](https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64)

*Sources: [vars/AlmaLinux.yml](vars/AlmaLinux.yml#L14-L67)*

### **Rocky Linux**
- Uses **Rocky Linux's official repositories** (`baseos`, `appstream`, `crb`) and **EPEL** for additional packages.
- **RPM Fusion** and **NVIDIA CUDA** repositories are configured similarly to AlmaLinux but with Rocky-specific paths.
- **Example Repositories**:
  - `rocky-baseos`: [https://dl.rockylinux.org/pub/rocky/10/BaseOS/x86_64/os/](https://dl.rockylinux.org/pub/rocky/10/BaseOS/x86_64/os/)
  - `epel`: [https://mirror.us.leaseweb.net/epel/10/Everything/x86_64/](https://mirror.us.leaseweb.net/epel/10/Everything/x86_64/)
  - `cuda-el10-x86_64`: [https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64](https://developer.download.nvidia.com/compute/cuda/repos/rhel10/x86_64)

*Sources: [vars/Rocky.yml](vars/Rocky.yml#L14-L90)*

---

## **2.3. GPG Key Strategy**
The role ensures **secure package installation** by verifying GPG keys for all repositories. The strategy differs slightly between distributions:

| Distribution  | GPG Key Source                                                                 | Example Key URL                                                                 |
|---------------|-------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| **Fedora**    | Bundled in `/usr/share/distribution-gpg-keys/` or fetched via HTTPS          | `file:///usr/share/distribution-gpg-keys/fedora/RPM-GPG-KEY-fedora-43-primary` |
| **AlmaLinux** | Bundled in `/usr/share/distribution-gpg-keys/` or fetched via HTTPS          | `file:///usr/share/distribution-gpg-keys/alma/RPM-GPG-KEY-AlmaLinux-10`        |
| **Rocky Linux** | Bundled in `/usr/share/distribution-gpg-keys/` or fetched via HTTPS          | `file:///usr/share/distribution-gpg-keys/rocky/RPM-GPG-KEY-Rocky-10`           |

**Key Takeaway**:
The role prefers **locally bundled keys** (installed via the `distribution-gpg-keys` package) but falls back to **HTTPS-fetched keys** for repositories not included in the bundle.
*Sources: [vars/Fedora.yml](vars/Fedora.yml#L5-L17), [vars/AlmaLinux.yml](vars/AlmaLinux.yml#L9-L12), [vars/Rocky.yml](vars/Rocky.yml#L8-L11)*

---

## **2.4. Build Mode Compatibility**
The role supports **two primary build modes**:
1. **Traditional ISO** (`minimal-installer` for Fedora, `image-installer` for AlmaLinux/Rocky).
2. **Bootc Container Image** (for atomic updates, supported on all distributions).

| Distribution  | Traditional ISO Type       | Bootc Support | Notes                                                                 |
|---------------|----------------------------|---------------|-----------------------------------------------------------------------|
| **Fedora**    | `minimal-installer`        | ✅ Yes         | Fedora-specific ISO type.                                             |
| **AlmaLinux** | `image-installer`          | ✅ Yes         | Uses RHEL-compatible ISO type.                                        |
| **Rocky Linux** | `image-installer`        | ✅ Yes         | Uses RHEL-compatible ISO type.                                        |

**Key Takeaway**:
The role **automatically selects the correct ISO type** based on the distribution. For example, Fedora uses `minimal-installer`, while AlmaLinux and Rocky Linux use `image-installer`.
*Sources: [defaults/main.yml](defaults/main.yml#L44), [tasks/select_build_mode.yml](tasks/select_build_mode.yml#L15-L22)*

---

## **3. Distribution-Specific Components**
The role allows **customization** of the build output using **components** (e.g., `gnome`, `nvidia`, `development`). Some components are **distribution-aware** and adapt their behavior accordingly.

### **3.1. NVIDIA Component**
The `nvidia` component is a great example of **distribution-aware logic**. It configures:
- **NVIDIA proprietary drivers** (via RPM Fusion or ELRepo).
- **CUDA repositories** (Fedora uses `fedora43`, while AlmaLinux/Rocky use `rhel10`).
- **Container Toolkit** (distro-agnostic).

**Example**:
For **Fedora**, the `nvidia` component adds:
```yaml
sources:
  - rpmfusion-nonfree-nvidia-driver
  - cuda-fedora43-x86_64
  - nvidia-container-toolkit
```
For **AlmaLinux/Rocky**, it adds:
```yaml
sources:
  - rpmfusion-nonfree-nvidia-driver
  - cuda-el10-x86_64
  - nvidia-container-toolkit
```
*Sources: [defaults/main.yml](defaults/main.yml#L70-L82), [vars/Fedora.yml](vars/Fedora.yml#L44-L58), [vars/AlmaLinux.yml](vars/AlmaLinux.yml#L48-L55)*

---

## **4. How to Select a Distribution for Your Build**
The distribution is selected via the `osbuild_distro` variable, which follows this format:
- **Fedora**: `fedora-<version>` (e.g., `fedora-43`).
- **AlmaLinux**: `almalinux-<version>` (e.g., `almalinux-10.2`).
- **Rocky Linux**: `rocky-<version>` (e.g., `rocky-10.2`).

**Example Playbook**:
```yaml
- hosts: build_host
  vars:
    osbuild_distro: "almalinux-10.2"  # Build an AlmaLinux 10.2 image
    osbuild_components:
      - base
      - gnome
      - nvidia
  roles:
    - osbuild
```
*Sources: [defaults/main.yml](defaults/main.yml#L14)*

---

## **5. Key Differences Between Distributions**
This table summarizes the **key differences** between the supported distributions:

| Feature                | Fedora                          | AlmaLinux                      | Rocky Linux                     |
|------------------------|---------------------------------|--------------------------------|---------------------------------|
| **Release Cycle**      | 6 months                        | 10 years (RHEL-compatible)     | 10 years (RHEL-compatible)      |
| **Repository Ecosystem** | Fedora + RPM Fusion           | AlmaLinux + EPEL + RPM Fusion  | Rocky Linux + EPEL + RPM Fusion |
| **Default ISO Type**   | `minimal-installer`             | `image-installer`              | `image-installer`               |
| **NVIDIA CUDA Path**   | `fedora43`                      | `rhel10`                       | `rhel10`                        |
| **GPG Key Source**     | Bundled or HTTPS                | Bundled or HTTPS               | Bundled or HTTPS                |
| **Use Case**           | Development, desktop            | Enterprise, server             | Enterprise, server              |

*Sources: [vars/Fedora.yml](vars/Fedora.yml), [vars/AlmaLinux.yml](vars/AlmaLinux.yml), [vars/Rocky.yml](vars/Rocky.yml)*

---

## **6. Next Steps**
Now that you understand the **supported distributions** and their configurations, you can:
1. **[Distribution-Specific Variables and Configurations](18-distribution-specific-variables-and-configurations)**: Learn how to customize variables for each distribution.
2. **[Adding Support for New Distributions](19-adding-support-for-new-distributions)**: Explore how to extend the role to support additional Linux distributions.
3. **[Build Modes: Selecting and Configuring for Your Use Case](8-build-modes-selecting-and-configuring-for-your-use-case)**: Dive deeper into the build modes available for each distribution.

---