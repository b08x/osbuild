This page explains how to integrate **custom packages and repositories** into your OSBuild-generated images. It covers the **component-based package taxonomy**, **repository source definitions**, **GPG key management**, and **blueprint injection** for both traditional ISO and bootc container images.

This documentation is **architecture-focused** and assumes familiarity with:
- [Default Variables and Overrides in `defaults/main.yml`](9-default-variables-and-overrides-in-defaults-main-yml)
- [Managing Repositories and GPG Keys](10-managing-repositories-and-gpg-keys)
- [Blueprint Creation and Validation](13-blueprint-creation-and-validation)

---

## 1. Core Concept: Component-Based Package Taxonomy

### **1.1. Component as the Unit of Customization**
The OSBuild role uses a **component-driven architecture** to define packages, services, and repositories. Each component is a **self-contained unit** that declares its dependencies, conflicts, and build-time impacts.

**Key files**:
- `defaults/main.yml` (lines 152-200): Defines the **primary interface** for component selection via `osbuild_components`.
- `vars/Fedora.yml`, `vars/AlmaLinux.yml`, `vars/Rocky.yml`: Contain **distribution-specific repository definitions** and **component taxonomies**.

---

### **1.2. Component Schema**
Each component is defined in the `osbuild_component_defs` dictionary (loaded from distribution-specific vars) and follows this schema:

| Field               | Type         | Description                                                                                     | Example                                                                                     |
|---------------------|--------------|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `label`             | string       | Human-readable name.                                                                            | `"NVIDIA Driver + CUDA"`                                                                    |
| `packages`          | list/Jinja2  | Package names or Jinja2 expressions resolving to a list.                                       | `["nvidia-driver", "cuda"]`                                                                 |
| `blueprint_groups`  | list         | DNF group names.                                                                                | `["gnome-desktop"]`                                                                         |
| `services`          | list         | Systemd services to enable.                                                                     | `["nvidia-persistenced"]`                                                                  |
| `kernel_args`       | list         | Kernel command-line arguments.                                                                  | `["rd.driver.blacklist=nouveau"]`                                                           |
| `sources`           | list         | Repository source names (keys in the `repo` dictionary).                                        | `["rpmfusion-nonfree-nvidia-driver", "cuda-fedora43-x86_64"]`                               |
| `files`             | list         | Custom file payloads (embedded in blueprint).                                                   | `[{path: "/etc/modprobe.d/nvidia.conf", content: "blacklist nouveau", mode: "0644"}]`       |
| `flatpaks`          | list         | Flatpak application IDs.                                                                        | `["org.gnome.Calculator"]`                                                                  |
| `copr_repos`        | list         | COPR repository names.                                                                          | `["atim/starship"]`                                                                         |
| `bootc_repos`       | list         | Shell commands to add repos in bootc builds.                                                    | See `defaults/main.yml` lines 86-150.                                                       |
| `requires`          | list         | Component dependencies.                                                                         | `["base"]`                                                                                  |
| `conflicts`         | list         | Component conflicts.                                                                            | `["nouveau"]`                                                                               |
| `size_impact`       | enum         | Estimated ISO size impact: `"none"`, `"small"`, `"medium"`, `"large"`.                         | `"large"` (for `oneapi`)                                                                    |
| `build_time_impact` | enum         | Estimated build time impact: `"none"`, `"low"`, `"medium"`, `"high"`.                          | `"high"` (for `oneapi`)                                                                     |

**Sources**:
- [defaults/main.yml#L152-L200](defaults/main.yml#L152-L200)
- [vars/Fedora.yml#L1-79](vars/Fedora.yml#L1-79)
- [vars/AlmaLinux.yml#L1-68](vars/AlmaLinux.yml#L1-68)
- [vars/Rocky.yml#L1-90](vars/Rocky.yml#L1-90)

---

### **1.3. Component Selection Interface**
The `osbuild_components` list in `defaults/main.yml` is the **primary interface** for customization. To add or remove packages, **modify this list** rather than editing individual package lists.

**Example**:
```yaml
osbuild_components:
  - base
  - gnome
  - nvidia
  - development
  - container-tools
  - cli-tools  # Adds modern CLI utilities (fd, dust, zoxide, etc.)
```

**Sources**:
- [defaults/main.yml#L172-L180](defaults/main.yml#L172-L180)

---

## 2. Repository Source Definitions

### **2.1. Repository Dictionary Structure**
Repositories are defined in **distribution-specific vars files** (`vars/Fedora.yml`, `vars/AlmaLinux.yml`, `vars/Rocky.yml`) under the `repo` dictionary. Each repository entry supports:

| Field         | Type    | Description                                                                                     | Example                                                                                     |
|---------------|---------|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `metalink`    | string  | Metalink URL for mirror-based downloads.                                                        | `"https://mirrors.fedoraproject.org/metalink?repo=fedora-43&arch=x86_64"`                  |
| `baseurl`     | string  | Direct repository URL.                                                                          | `"http://download1.rpmfusion.org/free/fedora/releases/43/Everything/x86_64/os/"`           |
| `gpgkey_url`  | string  | URL to the GPG key (supports `file://`, `https://`, `http://`).                                 | `"file:///usr/share/distribution-gpg-keys/fedora/RPM-GPG-KEY-fedora-43-primary"`           |
| `check_gpg`   | boolean | Whether to verify GPG signatures.                                                               | `true`                                                                                      |

**Sources**:
- [vars/Fedora.yml#L19-L79](vars/Fedora.yml#L19-L79)
- [vars/AlmaLinux.yml#L14-L68](vars/AlmaLinux.yml#L14-L68)
- [vars/Rocky.yml#L17-L90](vars/Rocky.yml#L17-L90)

---

### **2.2. Dynamic Repository URL Aggregation**
The `tasks/sources.yml` playbook **aggregates repository URLs** from the `repo` dictionary based on the `sources` field of selected components. This ensures that only **required repositories** are included in the build.

**Key logic**:
- Repositories are **unioned** with `osbuild_extra_repo_urls` (for caller-provided URLs).
- URLs are **deduplicated** and **validated** at runtime.

**Example**:
If the `nvidia` component is selected, the following repositories are automatically included:
- `rpmfusion-nonfree-nvidia-driver`
- `cuda-fedora43-x86_64` (Fedora) or `cuda-el10-x86_64` (AlmaLinux/Rocky)
- `nvidia-container-toolkit`

**Sources**:
- [tasks/sources.yml#L6-L24](tasks/sources.yml#L6-L24)

---

## 3. GPG Key Management

### **3.1. Runtime GPG Key Fetching**
The `tasks/repo_keys.yml` playbook **fetches and validates GPG keys** at build time. Keys are:
- Downloaded from `gpgkey_url` (supports `file://`, `https://`, `http://`).
- Validated for **PGP markers** (`-----BEGIN PGP PUBLIC KEY BLOCK-----`).
- Stored in `repo_gpgkeys` for use in the blueprint.

**Key features**:
- **Idempotent**: Keys are cached in `osbuild_gpgkey_cache_dir` and reused if present.
- **Fail-fast**: Missing or malformed keys **abort the build** with a clear error message.
- **Parallel**: Keys are fetched concurrently (Ansible `forks: 10`).

**Sources**:
- [tasks/repo_keys.yml#L20-L116](tasks/repo_keys.yml#L20-L116)

---

### **3.2. GPG Key Strategy by Distribution**
| Distribution | Key Source Strategy                                                                             | Example                                                                                     |
|--------------|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| Fedora       | Prefer `file://` URLs from `distribution-gpg-keys` package. Fall back to `https://`.            | `file:///usr/share/distribution-gpg-keys/fedora/RPM-GPG-KEY-fedora-43-primary`             |
| AlmaLinux    | Prefer `file://` URLs from `distribution-gpg-keys` package. Fall back to `https://`.            | `file:///usr/share/distribution-gpg-keys/alma/RPM-GPG-KEY-AlmaLinux-10`                    |
| Rocky        | Prefer `file://` URLs from `distribution-gpg-keys` package. Fall back to `https://`.            | `file:///usr/share/distribution-gpg-keys/rocky/RPM-GPG-KEY-Rocky-9`                        |

**Sources**:
- [vars/Fedora.yml#L22](vars/Fedora.yml#L22)
- [vars/AlmaLinux.yml#L17](vars/AlmaLinux.yml#L17)
- [vars/Rocky.yml#L22](vars/Rocky.yml#L22)

---

## 4. Blueprint Injection

### **4.1. Dynamic Blueprint Generation**
The `templates/blueprint.toml.j2` template **dynamically generates the blueprint** based on selected components. Packages, groups, services, and kernel arguments are **injected at runtime**.

**Key sections**:
1. **Packages**: Aggregated from `osbuild_component_defs[c].packages` for each selected component.
2. **Groups**: Aggregated from `osbuild_component_defs[c].blueprint_groups`.
3. **Services**: Aggregated from `osbuild_component_defs[c].services`.
4. **Kernel Arguments**: Aggregated from `osbuild_component_defs[c].kernel_args`.
5. **Custom Files**: Embedded from `osbuild_component_defs[c].files`.

**Example**:
```toml
[[packages]]
name = "nvidia-driver"
version = "*"

[[packages]]
name = "cuda"
version = "*"

[customizations.kernel]
append = "rd.driver.blacklist=nouveau nvidia-drm.modeset=1"
```

**Sources**:
- [templates/blueprint.toml.j2#L28-L57](templates/blueprint.toml.j2#L28-L57)

---

### **4.2. Bootc Repository Injection**
For **bootc container images**, repositories are injected via **shell commands** defined in `osbuild_component_defs[c].bootc_repos`. These commands are embedded in the `Containerfile.bootc.j2` template.

**Example** (Fedora NVIDIA repos):
```dockerfile
RUN cat > /etc/yum.repos.d/rpmfusion-nonfree-nvidia-driver.repo << 'REPOEOF'
[rpmfusion-nonfree-nvidia-driver]
name=RPM Fusion for Fedora 43 - Nonfree - NVIDIA Driver
baseurl=http://download1.rpmfusion.org/nonfree/fedora/nvidia-driver/43/x86_64/
enabled=1
type=rpm-md
gpgcheck=1
gpgkey=https://rpmfusion.org/keys/RPM-GPG-KEY-rpmfusion-nonfree-fedora-2020
REPOEOF
```

**Sources**:
- [defaults/main.yml#L86-L150](defaults/main.yml#L86-L150)
- [templates/Containerfile.bootc.j2](templates/Containerfile.bootc.j2) *(not shown in detail but referenced in architecture)*

---

### **4.3. Blueprint Components (Package Fragments)**

When `osbuild_blueprint_components` is set, packages are declared per component in `files/<distro>/<ver>/<arch>/components/<name>.yml` instead of one inline `packages = [...]` list. A component carries `packages` (`@name` is a comps group), `services`, `kernel_args`, `repo_urls` and an optional TOML `fragment` of `[[customizations.files]]` / `[[customizations.repositories]]` entries.

```yaml
label: "Multimedia codecs"
repo_urls: ["http://download1.rpmfusion.org/free/el/updates/10/x86_64"]
services: []
kernel_args: []
packages: ["ffmpeg", "x264", "x265"]
```

The role merges and de-duplicates these lists, renders them with `templates/blueprint-components.toml.j2`, and adds every selected component's `repo_urls` to `--extra-repo`, so dropping a component also drops its repositories. Rocky 10 ships eleven components split from the static NVIDIA workstation blueprint; both depsolve to the same 1715 RPMs. See `playbooks/osbuild-rocky-iso-nvidia-components.yml`.

Sources: [components.yml](tasks/components.yml), [blueprint-components.toml.j2](templates/blueprint-components.toml.j2), [defaults/main.yml](defaults/main.yml)

---

## 5. Adding Custom Packages and Repositories

### **5.1. Step-by-Step Workflow**
To integrate **custom packages and repositories**, follow this workflow:

1. **Define the Repository**:
   - Add the repository to the `repo` dictionary in the appropriate distribution vars file (`vars/Fedora.yml`, `vars/AlmaLinux.yml`, or `vars/Rocky.yml`).
   - Specify `baseurl` or `metalink`, `gpgkey_url`, and `check_gpg`.

2. **Create a Component**:
   - Define a new component in `osbuild_component_defs` (in the same vars file).
   - Specify `packages`, `sources`, and other fields as needed.

3. **Add the Component to `osbuild_components`**:
   - Append the component name to the `osbuild_components` list in `defaults/main.yml`.

4. **Test the Build**:
   - Run the playbook with the updated variables:
     ```bash
     ansible-playbook playbooks/osbuild.yml -e osbuild_components="['base', 'gnome', 'your_custom_component']"
     ```

---

### **5.2. Example: Adding a COPR Repository**
**Goal**: Add the `atim/starship` COPR repository and the `starship` package.

1. **Define the Repository** (`vars/Fedora.yml`):
   ```yaml
   repo:
     copr-atim-starship:
       baseurl: "https://download.copr.fedorainfracloud.org/results/atim/starship/fedora-$releasever-$basearch/"
       gpgkey_url: "https://download.copr.fedorainfracloud.org/results/atim/starship/pubkey.gpg"
       check_gpg: true
   ```

2. **Define the Component** (`vars/Fedora.yml`):
   ```yaml
   osbuild_component_defs:
     starship:
       label: "Starship Prompt"
       packages: ["starship"]
       sources: ["copr-atim-starship"]
       size_impact: "small"
       build_time_impact: "low"
   ```

3. **Add the Component to `osbuild_components`** (`defaults/main.yml`):
   ```yaml
   osbuild_components:
     - base
     - gnome
     - starship
   ```

4. **Test the Build**:
   ```bash
   ansible-playbook playbooks/osbuild.yml -e osbuild_distro="fedora-43"
   ```

**Sources**:
- [vars/Fedora.yml#L19-L79](vars/Fedora.yml#L19-L79)
- [defaults/main.yml#L172-L180](defaults/main.yml#L172-L180)

---

## 6. Advanced: Overriding Package Pins
The `osbuild_package_pins` dictionary (in `defaults/main.yml`) allows **version pinning** for packages. To pin a package to a specific version:

```yaml
osbuild_package_pins:
  kernel: "6.5.7-300.fc43"
  nvidia-driver: "535.113.01-1.fc43"
```

**Sources**:
- [templates/blueprint.toml.j2#L33](templates/blueprint.toml.j2#L33)

---

## 7. Troubleshooting

### **7.1. Common Issues and Solutions**
| Issue                                                                                     | Solution                                                                                     |
|-------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| **Repository not found** (404 error).                                                     | Verify the `baseurl` or `metalink` in the `repo` dictionary. Check for typos or distribution-specific paths. |
| **GPG key verification failed**.                                                          | Ensure the `gpgkey_url` is correct and the key is valid. Test with `curl -sSL <gpgkey_url>`. |
| **Package not found in repository**.                                                      | Verify the package name in the component definition. Check repository metadata with `dnf repoquery --repo=<repo_name>`. |
| **Blueprint TOML syntax error**.                                                          | Run the playbook with `-vvv` to see the generated blueprint. Validate with `python3 -m tomllib <blueprint.toml>`. |
| **Component conflicts**.                                                                   | Check the `conflicts` field in the component definition. Resolve by removing conflicting components from `osbuild_components`. |

**Sources**:
- [tasks/repo_keys.yml#L94-L108](tasks/repo_keys.yml#L94-L108)
- [tasks/blueprint.yml#L158-L174](tasks/blueprint.yml#L158-L174)

---

## 8. Next Steps
- **[Security Hardening in Image Builds](26-security-hardening-in-image-builds)**: Learn how to integrate security policies and hardening into your builds.
- **[Debugging Build Failures and Log Analysis](23-debugging-build-failures-and-log-analysis)**: Troubleshoot and optimize your builds.
- **[Extending the Role: Best Practices for Contributors](29-extending-the-role-best-practices-for-contributors)**: Contribute new components or distributions to the role.

**Sources**:
- [defaults/main.yml](defaults/main.yml)
- [vars/Fedora.yml](vars/Fedora.yml)
- [vars/AlmaLinux.yml](vars/AlmaLinux.yml)
- [vars/Rocky.yml](vars/Rocky.yml)
- [tasks/sources.yml](tasks/sources.yml)
- [tasks/repo_keys.yml](tasks/repo_keys.yml)
- [templates/blueprint.toml.j2](templates/blueprint.toml.j2)