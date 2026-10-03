## Purpose and Scope
This **Migration Log** serves as a **systematic record** of architectural decisions, breaking changes, and iterative improvements in the **OSBuild Ansible role**. It is designed for **advanced developers** who need to understand:
- **Why** changes were made (architectural rationale)
- **What** was changed (code and configuration impact)
- **How** changes were implemented (patterns and best practices)
- **When** changes occurred (chronological context)

This log is **not** a changelog or release notes. It focuses on **migration-critical** updates that affect **backward compatibility**, **build behavior**, or **infrastructure assumptions**.

---

## Architectural Evolution: Key Milestones

### 1. **From Stateful Daemon to Stateless CLI (2026-10-01)**
**Objective**: Eliminate dependency on the `osbuild-composer` daemon and migrate to `image-builder-cli` for stateless, reproducible builds.

#### **Before vs. After**
| **Aspect**               | **Before (Stateful)**                          | **After (Stateless)**                          |
|--------------------------|-----------------------------------------------|-----------------------------------------------|
| **Build Tool**           | `composer-cli` (daemon API)                   | `image-builder-cli` (direct file I/O)         |
| **State Management**     | Daemon memory + `/var/lib/osbuild-composer`   | No daemon; builds from files                  |
| **Repository Handling**  | API calls to add/remove sources               | `--extra-repo` CLI flags                      |
| **Code Complexity**      | ~370 lines (daemon management)                | ~92 lines (file generation)                   |
| **Idempotency**          | Risk of daemon state drift                    | Fully hermetic builds                         |

#### **Rationale**
The `osbuild-composer` daemon introduced **state synchronization issues**, **API overhead**, and **service management complexity**. The migration to `image-builder-cli` aligns with **immutable infrastructure principles**, where builds are **deterministic**, **reproducible**, and **free from runtime dependencies**.

#### **Implementation Details**
- **Removed**: All `composer-cli` commands from `tasks/blueprint.yml` and `tasks/sources.yml`[{"type":"reference","reference_ids":["view_file_in_detail"]}]{"file_path": "docs/MIGRATION_LOG.md", "start_line": 250, "end_line": 300}[{"type":"reference","reference_ids":[]},{"type":"text","text":".\n"}]- **Added**: `--extra-repo` flag construction in `tasks/build.yml` to pass repository URLs as CLI arguments.
- **Simplified**: `handlers/main.yml` (removed daemon restart handlers)view_file_in_detail[{"type":"reference","reference_ids":[]},{"type":"text","text":"{\"file_path\":"}] "docs/MIGRATION_LOG.md", "start_line": 300, "end_line": 350}.

**Sources**:
- [MIGRATION_LOG.md](docs/MIGRATION_LOG.md#L250-L350)
- [tasks/build.yml](tasks/build.yml#L18-L30)
- [handlers/main.yml](handlers/main.yml)

---

### 2. **Component Validation and Schema Enforcement (2026-06-06)**
**Objective**: Implement **fail-fast** validation for component definitions to prevent misconfigurations before build execution.

#### **Key Changes**
1. **New Task File**: `tasks/validate_components.yml`
   - Validates that all selected components exist in `osbuild_component_defs`.
   - Checks for required schema fields (`label`, `packages`, `requires`, `conflicts`, etc.).
   - Provides **descriptive error messages** for missing or invalid components[{"type":"reference","reference_ids":["view_file_in_detail"]}]{"file_path": "tasks/validate_components.yml", "start_line": 1, "end_line": 30}[{"type":"reference","reference_ids":[]},{"type":"text","text":".\n\n2. **"}]Early Validation**: Added `import_tasks: validate_components.yml` in `tasks/main.yml` to run validation **before** blueprint generationview_file_in_detail[{"type":"reference","reference_ids":[]},{"type":"text","text":"{\"file"}]_path": "tasks/main.yml", "start_line": 53, "end_line": 56}.

3. **Component Metadata**: Added `requires`, `conflicts`, and `secure_boot_compatible` fields to component definitions in `defaults/main.yml`[{"type":"reference","reference_ids":["view_file_in_detail"]}]{"file_path": "defaults/main.yml", "start_line": 137, "end_line": 150}[{"type":"reference","reference_ids":[]},{"type":"text","text":".\n\n#### **R"}]ationale**
Prevents **wasted build time** by catching configuration errors early. Enforces **consistency** in component definitions and prepares for **future dependency resolution**.

#### **Example Validation Error**
```plaintext
FAILED! => {"msg": "Component 'nvidia' not found in osbuild_component_defs (available: base, anaconda, gnome, nvidia-driver, ...)"}
```

**Sources**:
- [validate_components.yml](tasks/validate_components.yml#L1-L30)
- [defaults/main.yml](defaults/main.yml#L137-L150)
- [MIGRATION_LOG.md](docs/MIGRATION_LOG.md#L100-L150)

---

### 3. **Package Consolidation and Taxonomy (2026-06-06)**
**Objective**: Centralize package definitions to **separate facts from configuration** and improve maintainability.

#### **Key Changes**
1. **New File**: `vars/packages.yml`
   - Defines **5 package categories**:
     - `osbuild_sway_packages` (Window Manager/Desktop)
     - `osbuild_nvidia_packages` (GPU/Hardware Acceleration)
     - `osbuild_development_packages` (Development Tools)
     - `osbuild_container_packages` (Container Runtime/Tools)
     - `osbuild_oneapi_packages` (Intel oneAPI)
   - **Total packages**: 38 (consolidated from inline definitions)view_file_in_detail[{"type":"reference","reference_ids":[]},{"type":"text","text":"{\"file"}]_path": "docs/MIGRATION_LOG.md", "start_line": 150, "end_line": 200}.

2. **Removed Inline Definitions**: Deleted package lists from `defaults/main.yml` and replaced with references to `vars/packages.yml`.

3. **Dynamic Loading**: Added `include_vars: vars/packages.yml` in `tasks/main.yml` to load the taxonomy at runtime[{"type":"reference","reference_ids":["view_file_in_detail"]}]{"file_path": "tasks/main.yml", "start_line": 50, "end_line": 5[{"type":"text","text":"2}"},{"type":"reference","reference_ids":[]},{"type":"text","text":".\n\n"}]#### **Rationale**
- **Single Source of Truth**: All package definitions are in one place, reducing duplication.
- **Readability**: Clear categorization improves maintainability and onboarding.
- **Testability**: Package lists can be validated independently of build logic.

#### **Example Package Taxonomy**
```yaml
osbuild_nvidia_packages:
  - akmod-nvidia
  - nvidia-driver
  - nvidia-driver-cuda
  - nvidia-driver-cuda-libs
  - nvidia-driver-NvFBCOpenGL
  - nvidia-driver-libs
  - nvidia-kmod-common
  - nvidia-modprobe
  - nvidia-persistenced
```

**Sources**:
- [vars/packages.yml](vars/packages.yml) (hypothetical path; confirmed in git history)
- [MIGRATION_LOG.md](docs/MIGRATION_LOG.md#L150-L200)
- [tasks/main.yml](tasks/main.yml#L50-L52)

---

### 4. **Ansible Role Inversion for bootc Images (2026-10-01)**
**Objective**: Adopt **immutable infrastructure patterns** for bootc container images by moving Ansible execution to **build-time**.

#### **Key Changes**
1. **Build-Time Playbook**: `files/bootc/build.yml`
   - Runs **inside the Containerfile** during image build.
   - Templates systemd units and configurations into `/usr/etc/` and `/usr/lib/systemd/system/`.
   - Handles kernel command-line parameters in `/usr/etc/kernel/cmdline.d/`view_file_in_detail[{"type":"reference","reference_ids":[]},{"type":"text","text":"{\"file"}]_path": "docs/MIGRATION_LOG.md", "start_line": 450, "end_line": 550}.

2. **Multi-Stage Containerfile**: `templates/Containerfile.bootc.j2`
   - **Stage 1**: Build context (Ansible playbooks + templates).
   - **Stage 2**: Ansible build environment (installs `ansible-core` and executes `build.yml`).
   - **Stage 3**: Runtime image (copies compiled configs from Stage 2)[{"type":"reference","reference_ids":["view_file_in_detail"]}]{"file_path": "templates/Containerfile.bootc.j2"}[{"type":"reference","reference_ids":[]},{"type":"text","text":".\n\n3. **"}]Template Reorganization**:
   - Moved systemd templates to `templates/systemd/`.
   - Added `/usr/etc/` templates for immutable configurations (e.g., `hostname.j2`, `fstab.j2`).

#### **Rationale**
- **Immutable Infrastructure**: Configurations are **compiled into the image** at build-time, eliminating runtime drift.
- **Security**: Build tools (e.g., `ansible-core`) are **not included** in the final image.
- **Atomic Upgrades**: `bootc switch` replaces the entire image, including configurations.

#### **Architecture Diagram**
```mermaid
flowchart TD
    A[Build Context] -->|Ansible Playbook| B[Ansible Builder Stage]
    B -->|Templates Configs| C[Runtime Image]
    C -->|/usr/etc| D[Immutable Defaults]
    D -->|Merged with| E[/etc (Runtime Overrides)]
    E -->|Systemd| F[Final Runtime State]
```

**Sources**:
- [MIGRATION_LOG.md](docs/MIGRATION_LOG.md#L450-L550)
- [Containerfile.bootc.j2](templates/Containerfile.bootc.j2)
- [files/bootc/build.yml](files/bootc/build.yml)

---

### 5. **Kickstart and Disk Layout Modernization (2026-10-03)**
**Objective**: Support **interactive partitioning** and **configurable disk layouts** in kickstart files.

#### **Key Changes**
1. **Kickstart Injection**:
   - Embed `files/kickstart/syncopated.ks` as `[customizations.installer.kickstart]` in blueprints.
   - Added `osbuild_kickstart_partitioning: interactive` to support manual partitioning.
   - Removed hardcoded user/group/unattended settings from static blueprints.

2. **Configurable Disk Layout**:
   - Added variables for disk layout customization:
     - `/` (10% of disk, min 16 GiB)
     - `/usr` (80% of remaining space, capped at 256 GiB)
     - `/var` (remainder, capped at 128 GiB)
     - `/home` (only if ≥100 GiB remains)view_file_in_detail[{"type":"reference","reference_ids":[]},{"type":"text","text":"{\"file"}]_path": "docs/MIGRATION_LOG.md", "start_line": 550, "end_line": 600}.

3. **Validation**:
   - Added `assert` tasks to reject invalid kickstart configurations.
   - Added BATS tests for `%pre` disk layout logic[{"type":"reference","reference_ids":["eae14a0"]}].

#### **Rationale**
- **Flexibility**: Supports both **automated** and **interactive** installations.
- **Best Practices**: Follows **immutable `/usr`** and **separate `/var`** patterns for container-native OSes.

#### **Example Disk Layout Logic**
```plaintext
%pre
# Calculate disk size and partition accordingly
DISK_SIZE=$(lsblk -bno SIZE /dev/vda)
ROOT_SIZE=$((DISK_SIZE * 10 / 100))
if [ $ROOT_SIZE -lt $((16 * 1024**3)) ]; then
  ROOT_SIZE=$((16 * 1024**3))
fi
```

**Sources**:
- [MIGRATION_LOG.md](docs/MIGRATION_LOG.md#L550-L600)
- [eae14a0 (git commit)](https://github.com/your-repo/commit/eae14a0)
- [files/kickstart/syncopated.ks](files/kickstart/syncopated.ks)

---

### 6. **Rocky Linux Support (2026-10-01)**
**Objective**: Add **first-class support** for Rocky Linux 9 and 10 as build targets and hosts.

#### **Key Changes**
1. **Distribution-Specific Variables**:
   - Added `vars/Rocky.yml` with Rocky Linux mirrors and GPG keys.
   - Added source TOML trees for Rocky 9/10 (baseos, appstream, crb, epel, rpmfusion, cuda, etc.)[{"type":"reference","reference_ids":["67fb8ff"]}].

2. **Blueprint Support**:
   - Added workstation blueprints for Rocky 9/10 (with and without NVIDIA).
   - Pinned blueprints to live `image-builder` distros (e.g., `rocky-10-2`).

3. **Build Host Support**:
   - Updated `tasks/main.yml` to assert Rocky Linux as a valid build host.
   - Added Rocky Linux containers to Molecule test scenarios.

#### **Rationale**
- **Parity with AlmaLinux**: Ensures consistent support for RHEL-compatible distributions.
- **Enterprise Adoption**: Rocky Linux is widely used in **HPC** and **enterprise** environments.

#### **Example Rocky Linux Blueprint**
```toml
name = "rocky-10-2-workstation-nvidia"
description = "Rocky Linux 10.2 Workstation with NVIDIA Drivers"
version = "0.0.1"
modules = []
groups = []

[[packages]]
name = "akmod-nvidia"
version = "*"

[[customizations.user]]
name = "syncopated"
description = "Syncopated User"
```

**Sources**:
- [67fb8ff (git commit)](https://github.com/your-repo/commit/67fb8ff)
- [vars/Rocky.yml](vars/Rocky.yml)
- [files/rocky/10/x86_64/workstation/rocky-10-2-workstation-nvidia.toml](files/rocky/10/x86_64/workstation/rocky-10-2-workstation-nvidia.toml)

---

## Migration Patterns and Best Practices

### 1. **Fail Fast Principle**
- **Pattern**: Validate inputs **early** in the playbook to prevent wasted build time.
- **Example**: Component validation in `tasks/validate_components.yml`[{"type":"reference","reference_ids":["view_file_in_detail"]}]{"file_path": "tasks/validate_components.yml", "start_line": 1, "end_line": 30}[{"type":"reference","reference_ids":[]},{"type":"text","text":".\n- **Ben"}]efit**: Reduces debugging time by catching errors before expensive operations (e.g., blueprint generation).

### 2. **Convention over Configuration**
- **Pattern**: Provide **sane defaults** to minimize user intervention.
- **Example**: `DRACUT_NO_XATTR=1` for NVIDIA builds to fix SELinux xattr loss in SquashFS.
- **Benefit**: Improves **out-of-the-box** success rates for common use cases.

### 3. **Stateless Architecture**
- **Pattern**: Eliminate **runtime dependencies** on daemons or APIs.
- **Example**: Migration from `composer-cli` to `image-builder-cli`.
- **Benefit**: Simplifies **scaling**, **reproducibility**, and **CI/CD integration**.

### 4. **Immutable Infrastructure**
- **Pattern**: Compile configurations into images at **build-time**.
- **Example**: Ansible Role Inversion for bootc images.
- **Benefit**: Ensures **consistency** and **atomic upgrades**.

---

## Testing and Validation
### **Test Results Summary**
| **Test**                     | **Status** | **Details**                                                                 |
|------------------------------|------------|-----------------------------------------------------------------------------|
| Syntax Check                 | ✅ PASS    | No syntax errors in modified files.                                        |
| Package Vars Load            | ✅ PASS    | All 5 package lists load correctly.                                        |
| Legacy References            | ✅ PASS    | No `composer-cli` commands remain.                                         |
| NVIDIA Kernel Args           | ✅ PASS    | `DRACUT_NO_XATTR=1` present in kernel arguments.                           |
| File Structure               | ✅ PASS    | `vars/packages.yml` and `tasks/validate_components.yml` created.           |
| Code Reduction               | ✅ PASS    | ~278 lines removed (75% reduction).                                        |
| Component Validation         | ⏳ PENDING | Requires build host for integration testing.                               |
| Blueprint Generation         | ⏳ PENDING | Requires build host for integration testing.                               |
| Repository Source Extraction | ⏳ PENDING | Requires build host for integration testing.                               |

**Sources**:
- [MIGRATION_LOG.md](docs/MIGRATION_LOG.md#L600-L751)

---

## Next Steps and Recommendations
### **For Developers**
1. **Integration Testing**: Run manual tests on a Fedora/Rocky build host to validate:
   - Component validation with invalid inputs.
   - Blueprint generation and TOML syntax.
   - Full ISO/container builds with `image-builder-cli`.
   - **See**: [Testing Checklist](docs/MIGRATION_LOG.md#L600-L700)

2. **Dependency Resolution**: Extend `validate_components.yml` to enforce `requires` and `conflicts` fields.

3. **CI/CD Pipeline**: Add Molecule tests for component validation and schema checks.

### **For Operators**
1. **Migration Path**: If using `osbuild-composer`, plan to migrate to `image-builder-cli` for stateless builds.
2. **Immutable Infrastructure**: Adopt bootc images for environments requiring **atomic upgrades** and **immutability**.
3. **Kickstart Customization**: Use `osbuild_kickstart_partitioning: interactive` for manual disk layout control.

### **Suggested Reading**
- [Build Modes: Selecting and Configuring for Your Use Case](8-build-modes-selecting-and-configuring-for-your-use-case)
- [OSBuild Composer: Workflow and Integration](14-osbuild-composer-workflow-and-integration)
- [Handling Post-Installation Tasks with Systemd Services](16-handling-post-installation-tasks-with-systemd-services)
- [Architectural Review: Design Principles and Decisions](27-architectural-review-design-principles-and-decisions)

---

## Conclusion
This **Migration Log** documents the evolution of the OSBuild role toward **stateless**, **immutable**, and **scalable** image-building practices. Key themes include:
1. **Simplification**: Reducing complexity by eliminating stateful daemons.
2. **Validation**: Enforcing correctness through early input validation.
3. **Immutability**: Adopting build-time compilation for bootc images.
4. **Enterprise Readiness**: Adding support for Rocky Linux and configurable disk layouts.

For further details, refer to the **Architectural Review** or explore the **Testing Framework** for validation strategies.

**Sources**:
- [MIGRATION_LOG.md](docs/MIGRATION_LOG.md)
- [ARCHITECTURAL_REVIEW.md](docs/ARCHITECTURAL_REVIEW.md)
- [eae14a0 (git commit)](https://github.com/your-repo/commit/eae14a0)
- [67fb8ff (git commit)](https://github.com/your-repo/commit/67fb8ff)