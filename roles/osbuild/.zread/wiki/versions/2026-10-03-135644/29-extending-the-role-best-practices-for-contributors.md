This page provides **architectural guidance** for contributors seeking to extend the `osbuild` role. It focuses on **patterns, conventions, and integration points** rather than step-by-step instructions. For implementation details, refer to the linked source files.

---

## 1. **Core Extension Patterns**
The role is designed around **three extensibility axes**:
1. **Component-Based Customization**: Add or modify *components* to alter package lists, services, or kernel arguments.
2. **Build Mode Expansion**: Introduce new build modes (e.g., cloud images, OCI artifacts).
3. **Distribution Support**: Add support for new Linux distributions (e.g., Debian, openSUSE).

### **Component Architecture**
Components are the **primary abstraction** for customization. Each component defines:
- Packages, services, and kernel arguments.
- Repository sources and file injections.
- Dependencies and conflicts.

**Key Files**:
- Component definitions: [`defaults/main.yml`](defaults/main.yml#L200-L869) (search for `osbuild_component_defs`).
- Blueprint template: [`templates/blueprint.toml.j2`](templates/blueprint.toml.j2#L1-L133).

#### **Component Schema**
Components adhere to a **strict schema** validated by [`tests/validate_schema.py`](tests/validate_schema.py#L1-L124). The schema includes:
| Field                     | Type               | Description                                                                 |
|---------------------------|--------------------|-----------------------------------------------------------------------------|
| `label`                   | String             | Human-readable name.                                                        |
| `packages`                | List/Jinja2        | Packages or Jinja2 expressions resolving to lists.                          |
| `blueprint_groups`        | List/Jinja2        | DNF groups for image-builder.                                               |
| `services`                | List/Jinja2        | Systemd services to enable.                                                 |
| `kernel_args`             | List/Jinja2        | Kernel command-line arguments.                                              |
| `sources`                 | List/Jinja2        | Repository sources required.                                                |
| `requires`/`conflicts`    | List               | Component dependencies/conflicts.                                           |
| `size_impact`             | Enum               | Estimated ISO size impact (`none`, `small`, `medium`, `large`).             |
| `secure_boot_compatible`  | Boolean            | Whether the component supports Secure Boot.                                 |
| `bootc_only`/`blueprint_only` | Boolean       | Restricts the component to specific build modes.                           |

**Example Component** (from `defaults/main.yml`):
```yaml
cli-tools:
  label: "Modern CLI Utilities"
  packages:
    - fd-find
    - dust
    - zoxide
    - micro
  services: []
  kernel_args: []
  sources: []
  requires: ["base"]
  conflicts: []
  size_impact: "small"
  build_time_impact: "low"
  secure_boot_compatible: true
  bootc_only: false
  blueprint_only: false
```
Sources: [`defaults/main.yml`](defaults/main.yml#L400-L420).

---

## 2. **Adding a New Component**
### **Step 1: Define the Component**
Add the component to `osbuild_component_defs` in [`defaults/main.yml`](defaults/main.yml#L200-L869). Ensure it adheres to the schema above.

### **Step 2: Update Component Selection**
Add the component name to the `osbuild_components` list in [`defaults/main.yml`](defaults/main.yml#L150-L170) to include it in the default build.

### **Step 3: Validate the Schema**
Run the schema validation test:
```bash
cd /home/b08x/WorkspaceV3/Syncopated/ansible/roles/osbuild
python3 tests/validate_schema.py
```
Sources: [`tests/validate_schema.py`](tests/validate_schema.py#L1-L124).

### **Step 4: Test the Component**
1. **Unit Test**: Add a test case to [`tests/validate_components.yml`](tests/validate_components.yml) to verify the component integrates correctly.
2. **Integration Test**: Run a full build with the component enabled:
   ```bash
   ansible-playbook -e osbuild_components=['base','your-component'] tests/test.yml
   ```

---

## 3. **Extending Build Modes**
The role supports **three build modes**, resolved in [`tasks/select_build_mode.yml`](tasks/select_build_mode.yml#L1-L33):
1. `bootc_image`: Builds a bootc container image.
2. `generate_only`: Generates blueprints and build scripts without executing the build.
3. `traditional_iso`: Builds a traditional ISO image.

### **Adding a New Build Mode**
1. **Define the Mode**:
   Add a new mode to the `osbuild_resolved_build_mode` fact in [`tasks/select_build_mode.yml`](tasks/select_build_mode.yml#L10-L20).
   Example:
   ```yaml
   osbuild_resolved_build_mode: >-
     {{
       osbuild_build_bootc
       | ternary('bootc_image',
         osbuild_only_generate
         | ternary('generate_only',
           osbuild_cloud_image
           | ternary('cloud_image', 'traditional_iso')
         )
       )
     }}
   ```

2. **Implement the Mode**:
   Add a new task block in [`tasks/main.yml`](tasks/main.yml#L100-L264) for the mode. Example:
   ```yaml
   - name: MODE cloud_image
     when: osbuild_resolved_build_mode == 'cloud_image'
     tags: always
     block:
       - name: Import cloud build tasks
         ansible.builtin.import_tasks: cloud.yml
   ```

3. **Test the Mode**:
   Add a validation test to [`tests/validate_build_modes.yml`](tests/validate_build_modes.yml#L1-L82). Example:
   ```yaml
   - name: Validate cloud_image mode selection
     hosts: host5
     gather_facts: false
     vars:
       osbuild_cloud_image: true
       osbuild_blueprint_name: dummy
       osbuild_distro: fedora-43
     tasks:
       - name: Resolve build mode
         ansible.builtin.include_tasks: ../tasks/select_build_mode.yml
       - name: Verify resolved mode
         ansible.builtin.assert:
           that:
             - osbuild_resolved_build_mode == 'cloud_image'
   ```

---

## 4. **Adding Support for New Distributions**
The role supports **Fedora, AlmaLinux, and Rocky Linux**. To add a new distribution (e.g., Debian):

### **Step 1: Add Distribution Variables**
Create a new variable file in [`vars/`](vars/) (e.g., `Debian.yml`). Define:
- Repository sources.
- GPG keys.
- Distribution-specific packages.

Example (from [`vars/Fedora.yml`](vars/Fedora.yml#L1-L79)):
```yaml
repo:
  fedora:
    metalink: "https://mirrors.fedoraproject.org/metalink?repo=fedora-43&arch=x86_64"
    gpgkey_url: "file:///usr/share/distribution-gpg-keys/fedora/RPM-GPG-KEY-fedora-43-primary"
    check_gpg: true
```

### **Step 2: Update Compatibility Checks**
Modify the compatibility check in [`tasks/main.yml`](tasks/main.yml#L30-L40):
```yaml
- name: Check operating system compatibility
  ansible.builtin.assert:
    that:
      - ansible_os_family in ["RedHat", "Debian"]
      - ansible_distribution in ["Fedora", "AlmaLinux", "Rocky", "Debian"]
```

### **Step 3: Add Distribution-Specific Logic**
Use Jinja2 conditionals in templates and tasks to handle distribution-specific logic. Example (from [`defaults/main.yml`](defaults/main.yml#L50-L60)):
```yaml
osbuild_image_type: >-
  {{
    'minimal-installer' if ansible_distribution == 'Fedora'
    else 'debian-iso' if ansible_distribution == 'Debian'
    else 'image-installer'
  }}
```

### **Step 4: Test the Distribution**
Add a test case to [`tests/`](tests/) to validate the new distribution. Example:
```yaml
- name: Test Debian build
  hosts: debian_host
  vars:
    osbuild_distro: "debian-12"
    osbuild_components: ["base", "gnome"]
  tasks:
    - name: Run osbuild role
      ansible.builtin.include_role:
        name: osbuild
```

---

## 5. **Template Customization**
The role uses **Jinja2 templates** for blueprints, kickstart files, and build scripts. Key templates:
| Template                          | Purpose                                                                                     | Source File                                      |
|-----------------------------------|---------------------------------------------------------------------------------------------|--------------------------------------------------|
| Blueprint                         | Defines packages, services, and customizations for image-builder.                          | [`templates/blueprint.toml.j2`](templates/blueprint.toml.j2) |
| Kickstart                         | Configures the Anaconda installer.                                                          | [`templates/kickstart.toml.j2`](templates/kickstart.toml.j2) |
| Build Script                      | Script to execute the build (used in `generate_only` mode).                                 | [`templates/image-builder-build.sh.j2`](templates/image-builder-build.sh.j2) |
| Firstboot Files                   | Files injected into the image for first-boot configuration.                                | [`templates/firstboot-files.toml.j2`](templates/firstboot-files.toml.j2) |
| NVIDIA CDI Script                 | Generates NVIDIA Container Device Interface (CDI) configuration.                           | [`templates/snippets/nvidia-cdi.sh.j2`](templates/snippets/nvidia-cdi.sh.j2) |

### **Best Practices for Templates**
1. **Use TOML Literal Strings**:
   TOML literal strings (`'''...'''`) are used for multi-line content (e.g., kickstart files). Ensure injected files **do not contain `'''`**, as this breaks the TOML syntax. This is validated in [`tasks/blueprint.yml`](tasks/blueprint.yml#L50-L60).

2. **Leverage Jinja2 Filters**:
   Use filters to manipulate data in templates. Example (from [`templates/blueprint.toml.j2`](templates/blueprint.toml.j2#L50-L60)):
   ```jinja2
   {% set ns = namespace(kargs=[]) %}
   {% for c in osbuild_components %}
   {% if c in osbuild_component_defs and osbuild_component_defs[c].kernel_args %}
   {% set ns.kargs = ns.kargs + [osbuild_component_defs[c].kernel_args] %}
   {% endif %}
   {% endfor %}
   {% if ns.kargs %}
   [customizations.kernel]
   append = "{{ ns.kargs | join(' ') }}"
   {% endif %}
   ```

3. **Modularize Templates**:
   Break templates into smaller, reusable snippets. Example:
   ```jinja2
   {% include 'snippets/nvidia-cdi.sh.j2' %}
   ```

---

## 6. **Testing and Validation**
### **Testing Framework**
The role uses **BATS (Bash Automated Testing System)** and **Python** for testing. Key test files:
| Test File                          | Purpose                                                                                     | Source File                                      |
|------------------------------------|---------------------------------------------------------------------------------------------|--------------------------------------------------|
| Schema Validation                  | Validates component definitions against the schema.                                         | [`tests/validate_schema.py`](tests/validate_schema.py) |
| Build Mode Validation              | Tests build mode resolution logic.                                                          | [`tests/validate_build_modes.yml`](tests/validate_build_modes.yml) |
| Kickstart Validation               | Validates kickstart file injection.                                                         | [`tests/kickstart/check_kickstart.py`](tests/kickstart/check_kickstart.py) |
| Firstboot Validation               | Validates firstboot script injection.                                                       | [`tests/firstboot/check_injection.py`](tests/firstboot/check_injection.py) |

### **Adding Tests**
1. **Unit Tests**:
   Add Python tests to [`tests/`](tests/) for validation logic. Example:
   ```python
   def test_component_schema():
       with open("../defaults/main.yml") as f:
           data = yaml.safe_load(f)
       assert "your-component" in data["osbuild_component_defs"]
   ```

2. **Integration Tests**:
   Add BATS tests to [`tests/kickstart/kickstart.bats`](tests/kickstart/kickstart.bats) or [`tests/firstboot/firstboot.bats`](tests/firstboot/firstboot.bats). Example:
   ```bash
   @test "Kickstart file contains partitioning logic" {
     run grep -q "%pre --interpreter=/usr/bin/bash" "$KICKSTART_FILE"
     [ "$status" -eq 0 ]
   }
   ```

3. **Run Tests**:
   ```bash
   cd /home/b08x/WorkspaceV3/Syncopated/ansible/roles/osbuild
   python3 tests/validate_schema.py
   bats tests/kickstart/kickstart.bats
   ansible-playbook tests/validate_build_modes.yml
   ```

---

## 7. **Architectural Best Practices**
### **Immutability and Build-Time Compilation**
The role is transitioning toward **immutable infrastructure** and **build-time compilation**. Key principles:
1. **Avoid Runtime Mutations**:
   Configuration should be **baked into the image** during the build process, not applied at runtime. Use `/usr/etc` for immutable overlays.
   Sources: [`docs/ARCHITECTURAL_REVIEW.md`](docs/ARCHITECTURAL_REVIEW.md#L200-L300).

2. **Leverage `image-builder-cli`**:
   Migrate from `osbuild-composer` to `image-builder-cli` for stateless builds. See [`docs/ARCHITECTURAL_REVIEW.md`](docs/ARCHITECTURAL_REVIEW.md#L100-L150) for details.

3. **Component Isolation**:
   Ensure components are **self-contained** and do not rely on implicit dependencies.

### **Performance Optimization**
1. **Minimize ISO Size**:
   Use the `size_impact` field in component definitions to track ISO size contributions. Avoid including large packages unless necessary.

2. **Parallelize Builds**:
   Use `async` and `poll` in Ansible tasks to parallelize builds where possible. Example (from [`tasks/build.yml`](tasks/build.yml#L50-L70)):
   ```yaml
   - name: Run image-builder with repository sources
     ansible.builtin.shell: >
       image-builder build {{ osbuild_image_type }}
       --distro {{ osbuild_distro }}
       --blueprint {{ osbuild_blueprint_name }}.toml
     args:
       chdir: "{{ osbuild_output_dir }}"
     async: "{{ osbuild_build_timeout }}"
     poll: 30
   ```

---

## 8. **Next Steps**
1. **Review the Architectural Review**:
   Read [`Architectural Review: Design Principles and Decisions`](27-architectural-review-design-principles-and-decisions) for deeper insights into the role's design.

2. **Explore Component Definitions**:
   Study [`Default Variables and Overrides in defaults/main.yml`](9-default-variables-and-overrides-in-defaults-main-yml) to understand how components are structured.

3. **Validate Your Changes**:
   Use [`Testing Framework: BATS and Python Tests`](20-testing-framework-bats-and-python-tests) to ensure your contributions are robust.

4. **Contribute to the Wiki**:
   Add your findings to the [`Migration Log: Tracking Changes and Updates`](28-migration-log-tracking-changes-and-updates) page.