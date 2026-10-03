The **Backward Compatibility Layer for Legacy Variables** in the `osbuild` Ansible role ensures seamless migration from the deprecated `osbuild-composer` workflow to the modern `image-builder-cli` workflow. This layer retains legacy variables, provides component aliases, and includes feature toggles to maintain compatibility with existing inventory, playbooks, and tests while enabling gradual adoption of modern practices.

---

## Legacy Variable Retention

The role explicitly retains **legacy variables** from the `osbuild-composer` era to prevent breaking changes for existing users. These variables are marked with `[COMPATIBILITY]` comments and deprecated notices, guiding users toward modern equivalents.

### Key Retained Variables
| Variable | Purpose | Migration Guidance | Source |
|----------|---------|---------------------|--------|
| `osbuild_blueprint_name` | Blueprint name for compose and output files | Prefer component/image-builder equivalents | [`defaults/main.yml`](defaults/main.yml#L20-L22) |
| `osbuild_blueprint_version` | Blueprint version metadata | Prefer component/image-builder equivalents | [`defaults/main.yml`](defaults/main.yml#L25-L27) |
| `osbuild_blueprint_description` | Blueprint description metadata | Prefer component/image-builder equivalents | [`defaults/main.yml`](defaults/main.yml#L30-L32) |
| `osbuild_image_type` | Image type for `image-builder` (e.g., `minimal-installer`, `image-installer`) | Keep overriding until all consumers migrate to the image-builder CLI type mapping | [`defaults/main.yml`](defaults/main.yml#L35-L45) |
| `osbuild_build_timeout` | Build timeout for composer orchestration | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L601-L604) |
| `osbuild_poll_interval` | Poll interval for build status checks | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L607-L610) |
| `osbuild_build_retries` | Number of build retry attempts | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L613-L616) |
| `osbuild_use_blueprint_template` | Use dynamic Jinja2 template or static blueprint file | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L640-L643) |
| `osbuild_static_blueprint_path` | Path to static blueprint file | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L646-L651) |
| `osbuild_blueprint_template` | Template path for dynamic blueprint generation | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L654-L657) |
| `osbuild_output_filename` | Filename for the final image | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L730-L733) |
| `osbuild_keep_logs` | Keep build logs on failure | Retained for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L740-L743) |

---
## Component Aliases for Backward Compatibility

The role includes **component aliases** to maintain compatibility with legacy configurations. These aliases duplicate their target definitions to ensure backward compatibility with existing playbooks and inventory files. However, they are marked with a `TODO` comment indicating that they will drift over time and should be refactored to use an `alias_of` + `combine()` merge pattern.

### Key Component Aliases
| Alias | Target | Purpose | Source |
|-------|--------|---------|--------|
| `core` | `base` | Pure alias for backward compatibility | [`defaults/main.yml`](defaults/main.yml#L435-L450) |
| `desktop` | `gnome` + overrides | Preset pattern with conflicts (e.g., conflicts with `sway`) and extra flatpaks | [`defaults/main.yml`](defaults/main.yml#L453-L473) |
| `audio` | Standalone component | Audio production tools, including packages, groups, and flatpaks | [`defaults/main.yml`](defaults/main.yml#L476-L495) |
| `virtualization` | Standalone component | Virtualization stack, including libvirt, QEMU, and networking tools | [`defaults/main.yml`](defaults/main.yml#L498-L518) |

---
## Feature Toggles Derived from Legacy Variables

The role derives **feature toggles** from the `osbuild_components` list to maintain backward compatibility with legacy workflows. These toggles enable or disable specific features dynamically based on the presence of legacy component names.

### Key Feature Toggles
| Toggle | Derived From | Purpose | Source |
|--------|--------------|---------|--------|
| `osbuild_use_nvidia` | `'nvidia' in osbuild_components` | Enable NVIDIA-specific configurations (e.g., kernel args, services) | [`defaults/main.yml`](defaults/main.yml#L50-L51) |
| `osbuild_use_sway` | `'sway' in osbuild_components` | Enable Sway-specific configurations | [`defaults/main.yml`](defaults/main.yml#L52-L53) |
| `osbuild_include_development_tools` | `'development' in osbuild_components` | Enable development tools (e.g., GCC, Python, Git) | [`defaults/main.yml`](defaults/main.yml#L54-L55) |
| `osbuild_include_container_tools` | `'container-tools' in osbuild_components` | Enable container tools (e.g., Podman, Buildah) | [`defaults/main.yml`](defaults/main.yml#L56-L57) |
| `osbuild_include_oneapi_in_image` | `'oneapi' in osbuild_components` | Enable Intel oneAPI | [`defaults/main.yml`](defaults/main.yml#L58-L59) |

---
## Build Mode Selection Logic

The role implements a **build mode selection** mechanism to resolve the build mode based on legacy and modern variables. This ensures compatibility with both `osbuild-composer` and `image-builder-cli` workflows.

### Build Mode Resolution
The role uses the following logic to determine the build mode:
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
- **`osbuild_build_bootc`**: If `true`, the role builds a **bootc container image**.
- **`osbuild_only_generate`**: If `true`, the role generates the blueprint and build script without executing the build.
- **Default**: Traditional ISO build.

Sources: [`tasks/select_build_mode.yml`](tasks/select_build_mode.yml#L10-L17)

---
## Legacy Package Taxonomy Consolidation

The role consolidates **legacy package lists** into a **centralized taxonomy** to avoid duplication and ensure consistency. Legacy flat lists (e.g., `osbuild_sway_packages`, `osbuild_nvidia_packages`) have been absorbed into the canonical taxonomy under `system_packages.*`.

### Key Changes
- **Legacy Lists**: Flat lists like `osbuild_sway_packages` and `osbuild_nvidia_packages` are deprecated.
- **Canonical Taxonomy**: Package lists are now defined in distribution-specific files (e.g., `../../vars/packages/Fedora.yml`).
- **Backward Compatibility**: The role loads the canonical taxonomy via:
  ```yaml
  include_vars: "{{ role_path }}/../../vars/packages/{{ ansible_distribution }}.yml"
  ```
  Sources: [`tasks/main.yml`](tasks/main.yml#L40-L45), [`vars/packages.yml`](vars/packages.yml#L1-L11)

---
## Migration Guidance

The role provides **explicit migration guidance** for users to transition from legacy variables to modern equivalents. This is documented in the comments of `defaults/main.yml` and the `docs/MIGRATION_LOG.md` file.

### Key Migration Paths
1. **From `osbuild-composer` to `image-builder-cli`**:
   - Replace `composer-cli` commands with `image-builder` commands.
   - Remove daemon management tasks (e.g., `osbuild-composer.service`).
   - Use `--extra-repo` flags instead of `composer-cli sources add`.
   Sources: [`docs/MIGRATION_LOG.md`](docs/MIGRATION_LOG.md#L100-L150), [`docs/ARCHITECTURAL_REVIEW.md`](docs/ARCHITECTURAL_REVIEW.md#L50-L100)

2. **From Static Blueprints to Dynamic Templating**:
   - Use `osbuild_use_blueprint_template: true` for dynamic Jinja2 templating.
   - Static blueprints are still supported for backward compatibility.
   Sources: [`defaults/main.yml`](defaults/main.yml#L640-L657)

---
## Deprecation Warnings and Future Refactoring

The role includes **deprecation warnings** and `TODO` comments to guide future refactoring efforts. These ensure that legacy variables and patterns are gradually phased out.

### Key Deprecation Notes
- **Component Aliases**: Marked as `TODO` to refactor using `alias_of` + `combine()` merge pattern to avoid duplication and drift.
  Sources: [`defaults/main.yml`](defaults/main.yml#L429-L433)
- **Legacy Variables**: Marked as `[COMPATIBILITY] Retained for backward compatibility` with explicit deprecation notices.
  Sources: [`defaults/main.yml`](defaults/main.yml#L20-L45)

---
## Architectural Relationships

The backward compatibility layer is deeply integrated into the role's architecture. Below is a **Mermaid diagram** illustrating the relationships between legacy variables, component aliases, build modes, and migration paths:

```mermaid
graph TD
    %% Legacy Variables
    A[Legacy Variables] -->|Retained for Compatibility| B[defaults/main.yml]
    A -->|Deprecated Notices| C[Migration Guidance]
    A -->|Feature Toggles| D[osbuild_components]

    %% Component Aliases
    E[Component Aliases] -->|core → base| F[Pure Alias]
    E -->|desktop → gnome| G[Preset Pattern with Conflicts]
    E -->|audio, virtualization| H[Standalone Components]

    %% Build Mode Selection
    I[Build Mode Selection] -->|osbuild_build_bootc| J[bootc_image]
    I -->|osbuild_only_generate| K[generate_only]
    I -->|Default| L[traditional_iso]

    %% Package Taxonomy
    M[Legacy Package Lists] -->|Absorbed into| N[Canonical Taxonomy]
    N -->|Loaded via| O[include_vars: vars/packages/{Distribution}.yml]

    %% Migration Path
    P[osbuild-composer] -->|Replace with| Q[image-builder-cli]
    P -->|Remove Daemon Management| R[Stateless CLI]
    P -->|Use --extra-repo Flags| S[Repository Sources]

    %% Style
    style A fill:#f9f,stroke:#333
    style E fill:#bbf,stroke:#333
    style I fill:#9f9,stroke:#333
    style M fill:#ff9,stroke:#333
    style P fill:#f99,stroke:#333
```

---
## Next Steps

To continue your journey through the `osbuild` role, consider exploring the following pages:
- **[Migration from osbuild-composer to image-builder-cli](25-migration-from-osbuild-composer-to-image-builder-cli)**: Learn how to transition from the legacy `osbuild-composer` workflow to the modern `image-builder-cli` workflow.
- **[Component Definitions: Schema, Dependencies, and Conflicts](15-component-definitions-schema-dependencies-and-conflicts)**: Understand the schema, dependencies, and conflicts of component definitions.
- **[Architectural Overview: Component-Based Design Philosophy](7-architectural-overview-component-based-design-philosophy)**: Explore the high-level architecture and design principles of the `osbuild` role.