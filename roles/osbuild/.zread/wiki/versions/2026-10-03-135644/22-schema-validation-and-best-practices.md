## Introduction to Schema Validation in OSBuild
The **OSBuild** role employs a **rigorous schema validation framework** to ensure that component definitions, blueprint configurations, and repository structures adhere to predefined standards. This validation occurs at **both runtime and build-time**, leveraging **Ansible tasks**, **Python-based schema checkers**, and **TOML parsing** to enforce consistency, dependency resolution, and conflict detection.

Schema validation is **not merely a syntactic check**—it is a **systemic safeguard** that guarantees:
- **Component integrity**: Every selected component must conform to a strict schema, ensuring that all required fields (e.g., `packages`, `services`, `requires`) are present and correctly typed.
- **Dependency resolution**: Components declare their dependencies explicitly, and the system enforces that these are satisfied before build execution.
- **Conflict detection**: Components can declare mutual exclusivity (e.g., `gnome` vs. `sway`), and the system prevents incompatible selections.
- **Repository and GPG key validation**: Repository definitions must include valid `gpgkey_url` and `check_gpg` settings, ensuring secure package sources.
- **Blueprint and Kickstart integrity**: Generated TOML blueprints and Kickstart files are validated for structural correctness and content accuracy.

This documentation dissects the **schema architecture**, **validation mechanisms**, and **best practices** for extending or modifying the system.

---

## Core Schema Architecture

### 1. **Component Definition Schema**
The **central schema** is defined in `defaults/main.yml` under the `osbuild_component_defs` key. Each component is a **structured object** with **16 required fields**, enforced by both **Ansible tasks** and a **Python validator**.

#### **Schema Fields and Validation Rules**
| Field                     | Type               | Description                                                                                     | Validation Rules                                                                                     |
|---------------------------|--------------------|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| `label`                   | String             | Human-readable name for the component.                                                          | Must be non-empty.                                                                                   |
| `packages`                | List[String]       | List of packages to install.                                                                    | Must be a list or a Jinja2 expression resolving to a list (e.g., `{{ nvidia_packages }}`).          |
| `blueprint_groups`        | List[String]       | DNF group names to include in the blueprint.                                                    | Must be a list or Jinja2 expression.                                                                 |
| `services`                | List[String]       | Systemd services to enable.                                                                     | Must be a list or Jinja2 expression.                                                                 |
| `kernel_args`             | List[String]       | Kernel command-line arguments.                                                                  | Must be a list or Jinja2 expression.                                                                 |
| `sources`                 | List[String]       | Repository sources required for the component.                                                  | Must be a list or Jinja2 expression.                                                                 |
| `files`                   | List[Object]       | Custom file payloads to inject into the image.                                                  | Must be a list of objects with `path`, `mode` (optional), and `content` fields.                      |
| `flatpaks`                | List[String]       | Flatpak application IDs to install.                                                             | Must be a list or Jinja2 expression.                                                                 |
| `copr_repos`              | List[String]       | COPR repository names to enable.                                                                | Must be a list or Jinja2 expression.                                                                 |
| `bootc_repos`             | List[String]       | Shell commands to add repositories in `bootc` builds.                                           | Must be a list or Jinja2 expression.                                                                 |
| `requires`                | List[String]       | Component names this component depends on.                                                      | Must be a list or Jinja2 expression. Dependencies must exist in `osbuild_component_defs`.            |
| `conflicts`               | List[String]       | Component names this component conflicts with.                                                  | Must be a list or Jinja2 expression. Conflicts must exist in `osbuild_component_defs`.              |
| `size_impact`             | String             | Estimated ISO size impact (`none`, `small`, `medium`, `large`).                                 | Must be one of the predefined values.                                                                |
| `build_time_impact`       | String             | Estimated build time impact (`none`, `low`, `medium`, `high`).                                  | Must be one of the predefined values.                                                                |
| `secure_boot_compatible`  | Boolean            | Whether the component is compatible with Secure Boot.                                           | Must be a boolean (`true`/`false`).                                                                  |
| `bootc_only`              | Boolean            | Whether the component is exclusive to `bootc` builds.                                           | Must be a boolean (`true`/`false`).                                                                  |
| `blueprint_only`          | Boolean            | Whether the component is exclusive to traditional ISO builds.                                   | Must be a boolean (`true`/`false`).                                                                  |

**Example Component Definition** (`defaults/main.yml#L250-L300`):
```yaml
nvidia:
  label: "NVIDIA proprietary driver + CUDA"
  packages: "{{ nvidia_packages }}"
  blueprint_groups: []
  services: ["nvidia-persistenced"]
  kernel_args: ["rd.driver.blacklist=nouveau", "modprobe.blacklist=nouveau", "nvidia-drm.modeset=1"]
  sources: "{{ _nvidia_sources }}"
  files:
    - path: "/usr/local/bin/nvidia-cdi-generate.sh"
      mode: "0755"
      content: "{{ lookup('template', 'snippets/nvidia-cdi.sh.j2') }}"
  flatpaks: []
  copr_repos: []
  bootc_repos: "{{ _nvidia_bootc_repos }}"
  requires: ["base"]
  conflicts: ["nouveau"]
  size_impact: "large"
  build_time_impact: "high"
  secure_boot_compatible: false
  bootc_only: false
  blueprint_only: false
```
Sources: [defaults/main.yml](defaults/main.yml#L250-L300)

---

### 2. **Repository Schema**
Repository definitions are **distribution-specific** and stored in `vars/` (e.g., `AlmaLinux.yml`, `Fedora.yml`, `Rocky.yml`). Each repository is a **structured object** with **3 required fields**:

| Field         | Type    | Description                                                                                     | Validation Rules                                                                                     |
|---------------|---------|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| `baseurl`     | String  | Base URL for the repository.                                                                    | Must be a valid URL (HTTP/HTTPS).                                                                    |
| `metalink`    | String  | Metalink URL for mirror-based repository resolution.                                            | Must be a valid URL (HTTP/HTTPS).                                                                    |
| `gpgkey_url`  | String  | URL or `file://` path to the GPG key.                                                           | Must be a valid URL or `file://` path. Omitted if `check_gpg: false`.                               |
| `check_gpg`   | Boolean | Whether to enforce GPG signature verification.                                                  | Must be a boolean (`true`/`false`).                                                                  |

**Example Repository Definition** (`vars/Fedora.yml#L20-L30`):
```yaml
repo:
  fedora:
    metalink: "https://mirrors.fedoraproject.org/metalink?repo=fedora-43&arch=x86_64"
    gpgkey_url: "file:///usr/share/distribution-gpg-keys/fedora/RPM-GPG-KEY-fedora-43-primary"
    check_gpg: true
```
Sources: [vars/Fedora.yml](vars/Fedora.yml#L20-L30)

---

### 3. **Blueprint and Kickstart Schema**
Generated blueprints (`blueprint.toml.j2`) and Kickstart files (`kickstart.toml.j2`) are **validated for structural correctness** using **TOML parsing** and **content verification**.

#### **Blueprint Validation Rules**
- **TOML Syntax**: Must parse without errors.
- **No Forbidden Customizations**: Must not include `[[customizations.user]]`, `[[customizations.group]]`, or `installer.unattended`.
- **Anaconda Users Module**: Must enable `org.fedoraproject.Anaconda.Modules.Users`.
- **Sudoers Drop-In**: Must include `/etc/sudoers.d/90-wheel-nopasswd` with mode `0440` and correct content.
- **Kickstart Block**: Must include the Kickstart block exactly once if `osbuild_kickstart_enabled: true`.

**Validation Logic** (`tests/kickstart/check_kickstart.py#L40-L80`):
```python
USERS_MODULE = "org.fedoraproject.Anaconda.Modules.Users"
SUDOERS = "/etc/sudoers.d/90-wheel-nopasswd"

# Check for forbidden customizations
for key in ("user", "group"):
    if key in cust:
        err.append(f"has [[customizations.{key}]]")

# Check Anaconda Users module
if USERS_MODULE not in inst.get("modules", {}).get("enable", []):
    err.append("does not enable the Anaconda Users module")

# Check sudoers drop-in
sudoers = [f for f in cust.get("files", []) if f.get("path") == SUDOERS]
if len(sudoers) != 1 or sudoers[0].get("mode") != "0440":
    err.append(f"{SUDOERS} has wrong mode or data")
```
Sources: [tests/kickstart/check_kickstart.py](tests/kickstart/check_kickstart.py#L40-L80)

---

## Validation Mechanisms

### 1. **Python-Based Schema Validation**
The `tests/validate_schema.py` script performs **static schema validation** of `osbuild_component_defs` in `defaults/main.yml`. It enforces:
- **Presence of required fields**.
- **Type correctness** (e.g., `services` must be a list or Jinja2 expression).
- **Value constraints** (e.g., `size_impact` must be `none`, `small`, `medium`, or `large`).

**Key Validation Logic** (`tests/validate_schema.py#L20-L60`):
```python
REQUIRED_FIELDS = [
    "label", "packages", "blueprint_groups", "services", "kernel_args",
    "sources", "files", "flatpaks", "copr_repos", "bootc_repos",
    "requires", "conflicts", "size_impact", "build_time_impact",
    "secure_boot_compatible", "bootc_only", "blueprint_only"
]

LIST_FIELDS = [
    "blueprint_groups", "services", "kernel_args", "sources", "files",
    "flatpaks", "copr_repos", "bootc_repos", "requires", "conflicts"
]

VALID_SIZE = {"none", "small", "medium", "large"}
VALID_BUILD = {"none", "low", "medium", "high"}

for name, comp in sorted(defs.items()):
    missing = [f for f in REQUIRED_FIELDS if f not in comp]
    if missing:
        print(f"  FAIL {name}: missing {missing}")
        all_ok = False
        continue

    for lf in LIST_FIELDS:
        val = comp[lf]
        is_list = isinstance(val, list)
        is_jinja2_list = isinstance(val, str) and JINJA2_RE.search(val)
        if not is_list and not is_jinja2_list:
            print(f"  FAIL {name}: {lf} is {type(val).__name__}, expected list or Jinja2 list expression")
            all_ok = False
```
Sources: [tests/validate_schema.py](tests/validate_schema.py#L20-L60)

---

### 2. **Ansible-Based Runtime Validation**
The `tasks/validate_components.yml` playbook performs **runtime validation** of selected components (`osbuild_components`). It enforces:
- **Component existence**: All selected components must exist in `osbuild_component_defs`.
- **Schema compliance**: All required fields must be present.
- **Dependency resolution**: All `requires` must be satisfied.
- **Conflict detection**: No `conflicts` may be selected together.

**Key Validation Tasks** (`tasks/validate_components.yml#L5-L50`):
```yaml
- name: Check all components are defined
  ansible.builtin.assert:
    that: item in osbuild_component_defs.keys()
    fail_msg: "Component '{{ item }}' not found in osbuild_component_defs"
  loop: "{{ osbuild_components }}"

- name: Check for conflicting components selected together
  ansible.builtin.assert:
    that: item not in osbuild_components
    fail_msg: "Conflict detected: '{{ item }}' conflicts with a selected component"
  loop: "{{ _selected_conflicts | default([]) | unique }}"

- name: Check required dependencies are satisfied
  ansible.builtin.assert:
    that: (osbuild_component_defs[item].requires | default([])) | difference(osbuild_components) | length == 0
    fail_msg: "Component '{{ item }}' requires missing components: {{ (osbuild_component_defs[item].requires | default([])) | difference(osbuild_components) | join(', ') }}"
  loop: "{{ osbuild_components }}"
```
Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L5-L50)

---

### 3. **TOML and Kickstart Validation**
The `tests/kickstart/check_kickstart.py` and `tests/firstboot/check_injection.py` scripts validate **generated blueprints** for:
- **TOML syntax correctness**.
- **Kickstart content accuracy** (e.g., `lang`, `keyboard`, `timezone`).
- **Firstboot file injection** (e.g., `/usr/local/bin/syncopated-firstboot`).

**Kickstart Validation Logic** (`tests/kickstart/check_kickstart.py#L50-L90`):
```python
def strip_layout(contents):
    """Return contents without the layout %pre, or an error string."""
    if not contents.startswith(header):
        return None, "kickstart does not start with the lang/keyboard/timezone header"
    m = LAYOUT_RE.match(contents, len(header))
    if not m:
        return None, "layout %pre missing after the header"
    keys = [line.split("=")[0] for line in m.group(1).splitlines()]
    if keys != LAYOUT_KEYS:
        return None, f"layout keys {keys} != {LAYOUT_KEYS}"
    return header + contents[m.end():], None
```
Sources: [tests/kickstart/check_kickstart.py](tests/kickstart/check_kickstart.py#L50-L90)

---

## Best Practices for Schema Extensibility

### 1. **Adding a New Component**
To add a new component:
1. **Define the component** in `defaults/main.yml` under `osbuild_component_defs`.
2. **Declare all required fields** (see [Schema Fields Table](#core-schema-architecture)).
3. **Use Jinja2 expressions** for dynamic fields (e.g., `packages: "{{ my_packages }}"`).
4. **Test the component** by running:
   ```bash
   ansible-playbook tests/validate_schema.py
   ansible-playbook -e "osbuild_components=[base,new_component]" tests/test.yml
   ```

**Example: Adding a `kubernetes` Component**
```yaml
kubernetes:
  label: "Kubernetes Tools"
  packages: ["kubectl", "kubeadm", "kubelet"]
  blueprint_groups: []
  services: ["kubelet"]
  kernel_args: []
  sources: ["kubernetes"]
  files: []
  flatpaks: []
  copr_repos: []
  bootc_repos: []
  requires: ["base", "container-tools"]
  conflicts: []
  size_impact: "medium"
  build_time_impact: "medium"
  secure_boot_compatible: true
  bootc_only: false
  blueprint_only: false
```
Sources: [defaults/main.yml](defaults/main.yml#L300-L350) (hypothetical example)

---

### 2. **Adding a New Repository**
To add a new repository:
1. **Define the repository** in the appropriate `vars/` file (e.g., `Fedora.yml`).
2. **Specify `baseurl`/`metalink` and `gpgkey_url`**.
3. **Set `check_gpg: true`** unless the repository is unsigned.
4. **Test the repository** by running:
   ```bash
   ansible-playbook -e "osbuild_distro=fedora-43" tests/test.yml
   ```

**Example: Adding a `hashicorp` Repository**
```yaml
repo:
  hashicorp:
    baseurl: "https://rpm.releases.hashicorp.com/fedora/$releasever/$basearch/stable"
    gpgkey_url: "https://rpm.releases.hashicorp.com/gpg"
    check_gpg: true
```
Sources: [vars/Fedora.yml](vars/Fedora.yml#L80-L90) (hypothetical example)

---

### 3. **Modifying Blueprint or Kickstart Templates**
To modify templates (`blueprint.toml.j2`, `kickstart.toml.j2`):
1. **Edit the template** in `templates/`.
2. **Validate the template** by running:
   ```bash
   ansible-playbook tests/validate_kickstart_injection.yml
   ansible-playbook tests/validate_firstboot_injection.yml
   ```
3. **Ensure backward compatibility**—avoid breaking changes to existing fields.

**Example: Adding a Custom File to the Blueprint**
```jinja2
{% for c in osbuild_components %}
{% if c in osbuild_component_defs and osbuild_component_defs[c].files is defined %}
{% for f in osbuild_component_defs[c].files %}
[[customizations.files]]
path = "{{ f.path }}"
mode = "{{ f.mode | default('0644') }}"
data = '''
{{ f.content }}
'''
{% endfor %}
{% endif %}
{% endfor %}
```
Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L100-L120)

---

### 4. **Handling Dynamic Content with Jinja2**
- **Use Jinja2 expressions** for dynamic lists (e.g., `packages: "{{ nvidia_packages }}"`).
- **Leverage `namespace`** to aggregate values across components (e.g., `kernel_args`).
- **Avoid hardcoding values**—use variables from `defaults/main.yml` or `vars/`.

**Example: Aggregating Kernel Arguments**
```jinja2
{% set ns = namespace(kargs=[]) %}
{% for c in osbuild_components %}
{% if c in osbuild_component_defs and osbuild_component_defs[c].kernel_args is defined %}
{% set ns.kargs = ns.kargs + osbuild_component_defs[c].kernel_args %}
{% endif %}
{% endfor %}
{% if ns.kargs %}
[customizations.kernel]
append = "{{ ns.kargs | join(' ') }}"
{% endif %}
```
Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L50-L70)

---

## Testing and Validation Workflow

### 1. **Schema Validation**
Run the Python schema validator to check `osbuild_component_defs`:
```bash
./tests/validate_schema.py
```
**Output Example**:
```
Total components: 14

PASS: All 14 components validated successfully!
Component            Requires                          Conflicts                  Size     Build    SB BO BPO Svc Src
-------------------------------------------------------------------------------------------------------------------------------
anaconda             []                               []                         small    low      Y  N  Y    0   0
base                 []                               []                         small    low      Y  N  N    3   1
cli-tools            ['base']                         []                         small    low      Y  N  N    0   0
container-tools      ['base']                         []                         medium   medium   Y  N  N    1   1
development          ['base']                         []                         large    high     Y  N  N    0   0
docker               ['base']                         []                         medium   medium   Y  N  N    1   1
gnome                ['base']                         ['sway']                   large    high     Y  N  N    2   1
nvidia               ['base']                         ['nouveau']                large    high     N  N  N    1   3
oneapi               ['base']                         []                         large    high     Y  N  N    0   1
sway                 ['base']                         ['gnome']                  medium   medium   Y  N  N    1   0
```
Sources: [tests/validate_schema.py](tests/validate_schema.py#L80-L124)

---

### 2. **Runtime Validation**
Run the Ansible validation playbook to check selected components:
```bash
ansible-playbook -e "osbuild_components=[base,gnome,nvidia]" tests/validate_components.yml
```
**Output Example**:
```
TASK [Check all components are defined] *****************************************
ok: [localhost] => (item=base)
ok: [localhost] => (item=gnome)
ok: [localhost] => (item=nvidia)

TASK [Check for conflicting components selected together] ***********************
ok: [localhost] => (item=nouveau)

TASK [Check required dependencies are satisfied] ********************************
ok: [localhost] => (item=base)
ok: [localhost] => (item=gnome)
ok: [localhost] => (item=nvidia)

TASK [Display validated components with metadata] *******************************
ok: [localhost] => {
    "msg": [
        "✓ Validated 3 components: base, gnome, nvidia",
        "Size impacts: small, large, large",
        "Build time impacts: low, high, high"
    ]
}
```
Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L5-L69)

---

### 3. **Blueprint and Kickstart Validation**
Run the Kickstart and Firstboot validation scripts:
```bash
./tests/kickstart/check_kickstart.py _build/ kickstart/syncopated.ks 1 enabled en_US us "" UTC
./tests/firstboot/check_injection.py _build/ firstboot/ 1
```
**Output Example**:
```
ok blueprint-1.toml
ok blueprint-2.toml
```
Sources: [tests/kickstart/check_kickstart.py](tests/kickstart/check_kickstart.py#L100-L108), [tests/firstboot/check_injection.py](tests/firstboot/check_injection.py#L30-L47)

---

## Common Pitfalls and Debugging

### 1. **Schema Violations**
- **Error**: `FAIL my_component: missing ['requires']`
  **Solution**: Add the missing field to the component definition in `defaults/main.yml`.
  Sources: [tests/validate_schema.py](tests/validate_schema.py#L40-L50)

- **Error**: `FAIL my_component: services is str, expected list or Jinja2 list expression`
  **Solution**: Ensure `services` is a list or a Jinja2 expression (e.g., `services: "{{ my_services }}"`).
  Sources: [tests/validate_schema.py](tests/validate_schema.py#L50-L60)

---

### 2. **Dependency and Conflict Errors**
- **Error**: `Conflict detected: 'sway' conflicts with 'gnome'`
  **Solution**: Remove one of the conflicting components from `osbuild_components`.
  Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L30-L40)

- **Error**: `Component 'nvidia' requires ['base'] but missing: ['base']`
  **Solution**: Add `base` to `osbuild_components`.
  Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L40-L50)

---

### 3. **TOML and Kickstart Errors**
- **Error**: `blueprint-1.toml: invalid TOML: Expected '='`
  **Solution**: Check the template for syntax errors (e.g., missing `=` in `[[packages]]`).
  Sources: [tests/kickstart/check_kickstart.py](tests/kickstart/check_kickstart.py#L40-L50)

- **Error**: `kickstart does not start with the lang/keyboard/timezone header`
  **Solution**: Ensure `osbuild_locale`, `osbuild_keyboard`, and `osbuild_timezone` are set correctly.
  Sources: [tests/kickstart/check_kickstart.py](tests/kickstart/check_kickstart.py#L50-L60)

---

## Next Steps
- **[Debugging Build Failures and Log Analysis](23-debugging-build-failures-and-log-analysis)**: Learn how to diagnose and resolve build failures using logs and validation outputs.
- **[Extending the Role: Best Practices for Contributors](29-extending-the-role-best-practices-for-contributors)**: Explore advanced patterns for adding new components, repositories, or distributions.
- **[Architectural Review: Design Principles and Decisions](27-architectural-review-design-principles-and-decisions)**: Understand the high-level design choices behind the schema and validation architecture.