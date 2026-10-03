This page explains how the **OSBuild role** manages **distribution-specific variables and configurations** for **AlmaLinux, Fedora, and Rocky Linux**. It covers the **repository topology**, **GPG key strategy**, **dynamic variable resolution**, and **template specialization** that enable the role to support multiple distributions without hardcoding assumptions.

This documentation is **not** about:
- How to add a new distribution (see: [Adding Support for New Distributions](19-adding-support-for-new-distributions))
- How to customize blueprints or kickstart files (see: [Understanding Blueprints](6-understanding-blueprints-definition-and-customization) and [Kickstart Files](7-kickstart-files-automation-and-configuration))
- How to select build modes (see: [Build Modes](8-build-modes-selecting-and-configuring-for-your-use-case))

## **1. Repository Topology: The Core of Distribution Support**

Each supported distribution defines its **repository topology** in a dedicated `vars/[Distro].yml` file. These files are **not just lists of packages**—they encode the **mirror structure, GPG key strategy, and repository lifecycle** (e.g., major vs. point-release paths).

### **1.1. Repository Definition Schema**
Each repository is defined as a **YAML object** with the following schema:

| Field          | Type    | Description                                                                                     | Example                                                                                     |
|----------------|---------|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `metalink`     | string  | Metalink URL for mirror-based distribution (preferred for Fedora/AlmaLinux).                   | `"https://mirrors.fedoraproject.org/metalink?repo=fedora-43&arch=x86_64"`                  |
| `baseurl`      | string  | Direct base URL for the repository (used for EL distros and third-party repos).                 | `"https://dl.rockylinux.org/pub/rocky/10/BaseOS/x86_64/os/"`                              |
| `gpgkey_url`   | string  | URL or `file://` path to the GPG key. Omitted if `check_gpg: false`.                            | `"file:///usr/share/distribution-gpg-keys/alma/RPM-GPG-KEY-AlmaLinux-10"`                 |
| `check_gpg`    | boolean | Whether to verify packages with GPG. If `false`, `gpgkey_url` is omitted.                      | `true`                                                                                      |

Sources:
- [vars/AlmaLinux.yml](vars/AlmaLinux.yml#L14-L67)
- [vars/Fedora.yml](vars/Fedora.yml#L19-L78)
- [vars/Rocky.yml](vars/Rocky.yml#L17-L89)

---

### **1.2. Distribution-Specific Repository Topologies**

#### **AlmaLinux**
AlmaLinux uses **BaseOS, AppStream, and CRB (CodeReady Builder)** as its core repositories, supplemented by **EPEL** and **RPM Fusion for EL**. The repository paths are **point-release aware** (e.g., `almalinux-10.2`), but **EPEL and RPM Fusion use major-only paths** (e.g., `/epel/10/`).

Key repositories:
- `almalinux-baseos`: Base system packages.
- `almalinux-appstream`: Application streams (Python, Node.js, etc.).
- `almalinux-crb`: CodeReady Builder (development tools).
- `epel`: Extra Packages for Enterprise Linux.
- `rpmfusion-free-updates` / `rpmfusion-nonfree-updates`: Multimedia and proprietary drivers.

Sources:
- [vars/AlmaLinux.yml](vars/AlmaLinux.yml#L14-L47)

---

#### **Fedora**
Fedora uses **metalinks** for its core repositories (`fedora` and `updates`), supplemented by **RPM Fusion** (free/nonfree) and **COPR** for community packages. The repository paths are **version-aware** (e.g., `fedora-43`).

Key repositories:
- `fedora`: Base Fedora packages.
- `updates`: Updated packages for the current release.
- `rpmfusion-free` / `rpmfusion-nonfree`: Multimedia and proprietary drivers.
- `rpmfusion-nonfree-nvidia-driver`: NVIDIA proprietary drivers.
- `intel_oneAPI`: Intel oneAPI toolkit.
- `antigravity-rpm`: Custom third-party repository (GPG disabled).

Sources:
- [vars/Fedora.yml](vars/Fedora.yml#L19-L70)

---

#### **Rocky Linux**
Rocky Linux follows the **same repository topology as AlmaLinux** (BaseOS, AppStream, CRB, EPEL, RPM Fusion), differing only in **mirror URLs** and **GPG keys**. The repository paths are **major-version aware** (e.g., `/pub/rocky/10/`).

Key repositories:
- `rocky-baseos`: Base system packages.
- `rocky-appstream`: Application streams.
- `rocky-crb`: CodeReady Builder.
- `epel`: Extra Packages for Enterprise Linux.
- `rpmfusion-free-updates` / `rpmfusion-nonfree-updates`: Multimedia and proprietary drivers.

Sources:
- [vars/Rocky.yml](vars/Rocky.yml#L17-L53)

---

## **2. GPG Key Strategy: Secure Repository Verification**

The role uses a **consistent GPG key strategy** across all distributions:
- **Prefer `file://` URLs** for keys bundled in the `distribution-gpg-keys` package (e.g., `/usr/share/distribution-gpg-keys/`).
- **Use `https://` URLs** for keys not bundled (fetched at build time by `repo_keys.yml`).
- **Omit `gpgkey_url`** for repositories with `check_gpg: false` (e.g., `antigravity-rpm`).

### **2.1. GPG Key Fetching and Validation**
The `repo_keys.yml` task **fetches and validates GPG keys at build time**, ensuring that:
1. Each key is **reachable** (HTTP 200).
2. Each key contains a **valid PGP public key block** (checks for `-----END PGP PUBLIC KEY BLOCK-----`).
3. Keys are **stored in `/etc/osbuild-composer/repositories/`** for use by `osbuild-composer`.

Sources:
- [tasks/repo_keys.yml](tasks/repo_keys.yml) (not shown in inputs, but referenced in `tasks/main.yml#L73-L76`)

---

## **3. Dynamic Variable Resolution: Runtime Distribution Selection**

The role **does not hardcode distribution-specific logic**—instead, it **resolves variables dynamically** at runtime based on the `osbuild_distro` variable. This is achieved through:

### **3.1. Distribution Variable Loading**
The `tasks/main.yml` file **loads the correct `vars/[Distro].yml` file** based on the `ansible_distribution` fact:

```yaml
- name: Load distribution-specific repository variables
  ansible.builtin.include_vars:
    file: "vars/{{ ansible_distribution }}.yml"
```

This ensures that the **correct repository topology** is used for the **current build host’s distribution**.

Sources:
- [tasks/main.yml](tasks/main.yml#L55-L58)

---

### **3.2. Dynamic Variable Helpers in `defaults/main.yml`**
The `defaults/main.yml` file defines **helper variables** that **resolve dynamically** based on the distribution:

| Variable                     | Description                                                                                     | Example                                                                                     |
|------------------------------|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `_is_fedora`                 | Boolean flag for Fedora builds.                                                                 | `{{ ansible_distribution == 'Fedora' }}`                                                    |
| `_distro_version`            | Full version string (e.g., `10.2`).                                                             | `{{ osbuild_distro \| regex_replace('^[a-z]+-', '') }}`                                     |
| `_distro_major_version`      | Major version only (e.g., `10`).                                                                | `{{ _distro_version \| regex_replace('\\..*', '') }}`                                        |
| `_nvidia_sources`            | List of NVIDIA repositories, resolved dynamically for Fedora vs. EL.                           | See [defaults/main.yml](defaults/main.yml#L70-L82)                                          |
| `_nvidia_bootc_repos`        | Shell commands to add NVIDIA repos in bootc builds, resolved dynamically for Fedora vs. EL.    | See [defaults/main.yml](defaults/main.yml#L84-L150)                                         |

Sources:
- [defaults/main.yml](defaults/main.yml#L63-L150)

---

### **3.3. Component-Driven Repository Aggregation**
The role **aggregates repositories** from **selected components** (e.g., `nvidia`, `docker`, `oneapi`) at runtime. This is done in `tasks/main.yml`:

```yaml
- name: Compute aggregated sources from selected components
  ansible.builtin.set_fact:
    osbuild_component_sources: >
      {%- set ns = namespace(sources=[]) -%}
      {%- for c in osbuild_components -%}
      {%-   if c in osbuild_component_defs and osbuild_component_defs[c].sources is defined -%}
      {%-     set ns.sources = ns.sources + osbuild_component_defs[c].sources -%}
      {%-   endif -%}
      {%- endfor -%}
      {{ ns.sources | unique | list }}
```

This ensures that the **final repository set** is **not hardcoded**—it is **computed** from the intersection of:
1. The distribution’s base repositories (from `vars/[Distro].yml`).
2. The component’s required repositories (from `vars/packages.yml`).

Sources:
- [tasks/main.yml](tasks/main.yml#L82-L93)

---

## **4. Template Specialization: Distribution-Aware Blueprints and Kickstarts**

The role **specializes templates** for distributions **only where necessary**. This is achieved through **Jinja2 conditionals** in templates and **dynamic resolution** in `defaults/main.yml`.

### **4.1. Dynamic Image Type Resolution**
The `osbuild_image_type` variable is **resolved dynamically** based on the distribution:

```yaml
osbuild_image_type: "{{ 'minimal-installer' if ansible_distribution == 'Fedora' else 'image-installer' }}"
```

- **Fedora** uses `minimal-installer`.
- **EL distros (AlmaLinux, Rocky)** use `image-installer`.

Sources:
- [defaults/main.yml](defaults/main.yml#L44)

---

### **4.2. Distribution-Aware Kickstart Injection**
The `kickstart.toml.j2` template **injects distribution-specific variables** into the kickstart file, such as:
- `lang`, `keyboard`, and `timezone` (from `osbuild_locale`, `osbuild_keyboard`, and `osbuild_timezone`).
- **Disk layout variables** (e.g., `MIN_MIB`, `ROOT_PCT`) for auto-partitioning.

Sources:
- [templates/kickstart.toml.j2](templates/kickstart.toml.j2#L7-L26)

---

### **4.3. Blueprint Specialization for NVIDIA**
The `blueprint.toml.j2` template **specializes NVIDIA support** based on the distribution:
- **Fedora**: Uses `rpmfusion-nonfree-nvidia-driver` and `cuda-fedora{version}-x86_64`.
- **EL distros**: Uses `rpmfusion-nonfree-updates` and `cuda-el{major}-x86_64`.

This is **not hardcoded**—it is **resolved dynamically** using the `_nvidia_sources` helper variable.

Sources:
- [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L117-L132)
- [defaults/main.yml](defaults/main.yml#L70-L82)

---

## **5. Summary Table: Distribution-Specific Configurations**

| **Aspect**               | **AlmaLinux**                          | **Fedora**                              | **Rocky Linux**                         |
|--------------------------|----------------------------------------|-----------------------------------------|-----------------------------------------|
| **Core Repositories**    | BaseOS, AppStream, CRB                 | `fedora`, `updates`                     | BaseOS, AppStream, CRB                  |
| **EPEL Support**         | Yes (`epel`)                           | No                                      | Yes (`epel`)                            |
| **RPM Fusion**           | `rpmfusion-free-updates`               | `rpmfusion-free`, `rpmfusion-nonfree`   | `rpmfusion-free-updates`                |
| **NVIDIA Repo**          | `cuda-el{major}-x86_64`                | `cuda-fedora{version}-x86_64`           | `cuda-el{major}-x86_64`                 |
| **Image Type**           | `image-installer`                      | `minimal-installer`                     | `image-installer`                       |
| **GPG Key Strategy**     | `file://` for Alma keys, `https://` for others | `file://` for Fedora keys, `https://` for others | `file://` for Rocky keys, `https://` for others |
| **Kickstart Variables**  | Auto-partitioning with `MIN_MIB`       | Auto-partitioning with `MIN_MIB`        | Auto-partitioning with `MIN_MIB`        |

Sources:
- [vars/AlmaLinux.yml](vars/AlmaLinux.yml)
- [vars/Fedora.yml](vars/Fedora.yml)
- [vars/Rocky.yml](vars/Rocky.yml)
- [defaults/main.yml](defaults/main.yml#L44-L150)

---

## **6. Next Steps**

Now that you understand how **distribution-specific variables and configurations** work, you can explore:

- **[Adding Support for New Distributions](19-adding-support-for-new-distributions)**: Learn how to extend the role to support additional Linux distributions.
- **[Managing Repositories and GPG Keys](10-managing-repositories-and-gpg-keys)**: Dive deeper into repository management and GPG key validation.
- **[Build Modes](8-build-modes-selecting-and-configuring-for-your-use-case)**: Understand how to select and configure build modes for your use case.