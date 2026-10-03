This document provides a high-level architectural perspective on the **component-based design philosophy** underpinning the OSBuild Ansible role. The system employs a **modular, declarative approach** to image customization, where **components** serve as the primary abstraction for defining what gets included in both traditional ISO and bootc container builds. This design enables **reusability, maintainability, and scalability** while supporting complex build configurations across multiple distributions (Fedora, AlmaLinux, Rocky Linux).

---

## Core Design Principles

The architecture is built on **three foundational principles**:

1. **Component-Centric Abstraction**: Every feature or capability (e.g., NVIDIA GPU support, GNOME desktop, development tools) is encapsulated as a **component**. Components are **self-contained definitions** that declare their dependencies, conflicts, and contributions to the final image.
2. **Declarative Composition**: Users select components via the `osbuild_components` list. The system **dynamically aggregates** all required packages, services, kernel arguments, and repository sources from these selections.
3. **Build-Mode Agnosticism**: Components are designed to work across **both traditional ISO builds** (using `image-builder-cli`) and **bootc container builds**, with mode-specific logic handled transparently.

This philosophy ensures that the system remains **extensible**—new components can be added without modifying core logic—and **predictable**, as the final image is a deterministic function of the selected components.
Sources: [defaults/main.yml](defaults/main.yml#L200-L400)

---

## Component System Architecture

### Component Definition Schema
Each component in `osbuild_component_defs` adheres to a **strict schema** that defines its contributions to the build process. The schema includes the following fields:

| **Field**               | **Type**       | **Purpose**                                                                                     | **Example**                          |
|-------------------------|----------------|-------------------------------------------------------------------------------------------------|--------------------------------------|
| `label`                 | String         | Human-readable name for the component                                                          | `"NVIDIA GPU Stack"`                 |
| `packages`              | List           | Package names or Jinja2 expressions resolving to a list of packages to include               | `{{ system_packages.Graphics.nvidia }}` |
| `blueprint_groups`      | List           | DNF group names to include in the blueprint                                                    | `["development-tools", "c-development"]` |
| `services`              | List           | Systemd services to enable                                                                     | `["nvidia-persistenced", "gdm"]`      |
| `kernel_args`           | List           | Kernel command-line arguments to append                                                        | `["rd.driver.blacklist=nouveau"]`    |
| `sources`               | List           | Repository sources required by the component                                                   | `["rpmfusion-nonfree-nvidia-driver"]` |
| `files`                 | List           | Custom file payloads to inject into the image                                                  | `[{ path: "/etc/...", content: "..." }]` |
| `requires`              | List           | Components that must be included (dependencies)                                                | `["base"]`                            |
| `conflicts`             | List           | Components that cannot coexist with this one                                                  | `["sway"]` (for `desktop`)            |
| `size_impact`           | String         | Estimated impact on ISO size (`none`, `small`, `medium`, `large`)                              | `"large"`                            |
| `build_time_impact`     | String         | Estimated impact on build time (`none`, `low`, `medium`, `high`)                               | `"medium"`                           |
| `secure_boot_compatible`| Boolean        | Whether the component is compatible with Secure Boot                                          | `false` (for NVIDIA)                  |
| `bootc_only`            | Boolean        | If `true`, the component only applies to bootc builds                                          | `false`                              |
| `blueprint_only`        | Boolean        | If `true`, the component only applies to traditional ISO builds                                | `true` (for `anaconda`)               |

This schema ensures that every component **self-documents** its requirements and impacts, enabling **automated validation** and **user awareness** of build implications.
Sources: [defaults/main.yml](defaults/main.yml#L200-L220)

---

### Component Interaction Diagram
The following Mermaid diagram illustrates how components interact within the system:

```mermaid
graph TD
    %% Core Components
    base[base\n(Core System)] -->|requires| anaconda[anaconda\n(Installer)]
    base -->|requires| gnome[gnome\n(GNOME Desktop)]
    base -->|requires| sway[sway\n(Sway WM)]
    base -->|requires| nvidia[nvidia\n(NVIDIA GPU)]
    base -->|requires| development[development\n(Dev Tools)]
    base -->|requires| container-tools[container-tools\n(Container Runtime)]

    %% Conflicts
    gnome -->|conflicts| sway
    desktop[desktop\n(Alias for GNOME)] -->|conflicts| sway

    %% Dependencies
    nvidia -->|requires| base
    development -->|requires| base
    container-tools -->|requires| base

    %% Build Modes
    anaconda -->|blueprint_only| iso[Traditional ISO]
    nvidia -->|bootc_repos| bootc[bootc Container]
    base -->|bootc_only=false| iso
    base -->|bootc_only=false| bootc
```

**Key Observations**:
- The `base` component is the **foundational dependency** for all other components.
- **Conflicts** (e.g., `gnome` vs. `sway`) are explicitly declared to prevent invalid configurations.
- **Build-mode specificity** is handled via `bootc_only` and `blueprint_only` flags, ensuring components are only applied where appropriate.
Sources: [defaults/main.yml](defaults/main.yml#L200-L500)

---

## Dynamic Blueprint Generation

### Jinja2 Templating Engine
The system uses **Jinja2 templating** to dynamically generate **TOML-based blueprints** from the selected components. The primary template, [`blueprint.toml.j2`](templates/blueprint.toml.j2), iterates over `osbuild_components` and:
1. **Aggregates packages** from all components, respecting version pins (`osbuild_package_pins`).
2. **Merges kernel arguments** (e.g., NVIDIA-specific flags like `rd.driver.blacklist=nouveau`).
3. **Enables services** declared by components (e.g., `nvidia-persistenced`, `gdm`).
4. **Injects custom files** (e.g., NVIDIA CDI scripts, first-boot automation).
5. **Applies distribution-specific logic** (e.g., Fedora vs. AlmaLinux repository paths).

This approach ensures that the blueprint is **always consistent** with the selected components and their dependencies.
Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L1-L133)

---

### Blueprint Compilation Workflow
The following Mermaid flowchart illustrates the **blueprint generation process**:

```mermaid
flowchart TD
    A[Select Components\nosbuild_components] --> B[Validate Components\nvalidate_components.yml]
    B -->|Check| C{All Components\nDefined?}
    C -->|No| D[Fail: Undefined Component]
    C -->|Yes| E[Check Dependencies]
    E --> F{Dependencies\nSatisfied?}
    F -->|No| G[Fail: Missing Dependency]
    F -->|Yes| H[Check Conflicts]
    H --> I{Conflicts\nDetected?}
    I -->|Yes| J[Fail: Conflicting Components]
    I -->|No| K[Aggregate Component Data]
    K --> L[Render Blueprint\nblueprint.toml.j2]
    L --> M[Inject First-Boot Files\nfirstboot-files.toml.j2]
    M --> N[Inject Kickstart\nkickstart.toml.j2]
    N --> O[Validate TOML Syntax]
    O --> P[Final Blueprint\n{{ osbuild_blueprint_name }}.toml]
```

**Key Steps**:
1. **Validation**: The system first validates that all selected components are defined, their dependencies are satisfied, and no conflicts exist.
2. **Aggregation**: Packages, services, kernel arguments, and files from all components are **merged** into a unified structure.
3. **Templating**: The Jinja2 template renders the final TOML blueprint, including **dynamic injections** for first-boot automation and kickstart configurations.
4. **Validation**: The generated blueprint undergoes **TOML syntax validation** to ensure correctness.
Sources: [tasks/blueprint.yml](tasks/blueprint.yml#L1-L130), [tasks/validate_components.yml](tasks/validate_components.yml#L1-L69)

---

## Component Validation System

### Schema Validation
The system enforces **schema compliance** for all components, ensuring that:
- All required fields (`label`, `packages`, `requires`, `conflicts`, etc.) are present.
- Component names referenced in `requires` or `conflicts` are **valid and defined**.
- **Circular dependencies** are implicitly prevented by the validation logic.

This validation occurs **early** in the build process (via [`validate_components.yml`](tasks/validate_components.yml)), providing **fast feedback** on configuration errors.
Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L1-L69)

---

### Dependency and Conflict Resolution
The validation system performs **two critical checks**:
1. **Dependency Resolution**: For each component, it verifies that all components listed in `requires` are included in `osbuild_components`.
   - Example: If `nvidia` requires `base`, the system ensures `base` is selected.
2. **Conflict Detection**: It checks that no two selected components **conflict** with each other.
   - Example: Selecting both `gnome` and `sway` triggers a conflict error, as `gnome` (via the `desktop` alias) conflicts with `sway`.

This ensures that the **final component set is always internally consistent**.
Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L25-L60)

---

## Build-Mode Adaptability

### Traditional ISO vs. bootc Container
The component system is designed to **transparently support** both build modes:
- **Traditional ISO**: Uses `image-builder-cli` to create installer images (e.g., `minimal-installer` for Fedora, `image-installer` for AlmaLinux/Rocky).
  - Components like `anaconda` are **ISO-only** (`blueprint_only: true`).
- **bootc Container**: Creates **atomic OS container images** for immutable deployments.
  - Components like `nvidia` provide **bootc-specific repository configurations** (`bootc_repos`).

The **build mode is resolved** in [`select_build_mode.yml`](tasks/select_build_mode.yml), which sets `osbuild_resolved_build_mode` to one of:
- `traditional_iso`
- `bootc_image`
- `generate_only` (blueprint generation without building).

This resolution is **deterministic** and based on the `osbuild_build_bootc` and `osbuild_only_generate` flags.
Sources: [tasks/select_build_mode.yml](tasks/select_build_mode.yml#L1-L33)

---

## Distribution-Agnostic Design

### Cross-Distribution Support
The component system supports **Fedora, AlmaLinux, and Rocky Linux** through:
1. **Distribution-Specific Variables**: Each distribution has its own variable file (e.g., [`vars/Fedora.yml`](vars/Fedora.yml)) defining repository URLs, GPG keys, and package taxonomies.
2. **Dynamic Path Resolution**: The system uses `ansible_distribution` and `_distro_major_version` to resolve **distribution-specific paths** (e.g., for repository configurations).
3. **Package Taxonomy**: The `system_packages` structure (defined in `../../vars/packages/{Distribution}.yml`) provides **distribution-aware package lists** for each component.

This ensures that **the same component definitions work across all supported distributions** without modification.
Sources: [vars/Fedora.yml](vars/Fedora.yml#L1-L79), [defaults/main.yml](defaults/main.yml#L400-L600)

---
## Architectural Benefits

| **Benefit**               | **Implementation**                                                                                     | **Impact**                                                                                     |
|---------------------------|--------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| **Modularity**            | Components are self-contained and independently defined.                                              | Enables **easy addition/removal** of features without modifying core logic.                  |
| **Reusability**           | Components can be reused across builds and distributions.                                              | Reduces **duplication** and promotes **consistency**.                                         |
| **Validation**            | Automated schema, dependency, and conflict checking.                                                  | Catches **configuration errors early**, reducing build failures.                            |
| **Transparency**          | Components explicitly declare dependencies, conflicts, and impacts.                     | Users **understand the implications** of their selections.                                   |
| **Build-Mode Flexibility**| Components adapt to both traditional ISO and bootc container builds.                                    | Supports **multiple deployment models** with a single configuration.                       |
| **Distribution Agnostic**| Distribution-specific logic is isolated in variable files and package taxonomies.        | Enables **cross-distribution compatibility** with minimal overhead.                        |

---
## Next Steps

To deepen your understanding of the component-based architecture, proceed to:
- **[Component System: Modular Package and Configuration Management](10-component-system-modular-package-and-configuration-management)** for a detailed exploration of how components are defined, validated, and composed.
- **[Blueprint Generation: Dynamic TOML Templating with Jinja2](13-blueprint-generation-dynamic-toml-templating-with-jinja2)** to understand the templating engine that powers blueprint generation.
- **[Ansible Role Inversion Pattern for Immutable Infrastructure](8-ansible-role-inversion-pattern-for-immutable-infrastructure)** to see how this role integrates with broader immutable infrastructure patterns.

For hands-on implementation, refer to:
- **[Quick Start: Setting Up and Running Your First Image Build](2-quick-start-setting-up-and-running-your-first-image-build)** to apply these concepts in practice.
- **[Choosing the Right Build Mode for Your Use Case](6-choosing-the-right-build-mode-for-your-use-case)** to select the appropriate build mode for your needs.