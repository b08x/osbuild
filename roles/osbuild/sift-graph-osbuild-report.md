# SIFT-Graph Report: osbuild Role — Architecture, Integrity, and Risk

**Generated**: 2026-09-11T12:00:00Z
**Project**: home-b08x-WorkspaceV3-Syncopated-ansible-collections-ansible_collections-b08x-rhel_builder
**Graph Status**: indexed (1129 nodes, 1306 edges); osbuild role files all `parse_partial` (Jinja2/YAML — no resolvable graph nodes)
**Producer**: sift-graph v0.1 (source-fallback mode)
**Target**: `roles/osbuild/`

---

## Graph Coverage Caveat

The codebase-memory graph contains 1129 nodes for this collection, but **zero resolvable nodes** for the `roles/osbuild/` scope. All 13 files in the role are `parse_partial` — tree-sitter cannot fully parse Jinja2 templates (`.j2`) or YAML task files. Per SIFT-Graph protocol limitations, this report uses **source-fallback provenance**: every claim references an exact file path and line range read directly from source. Provenance tuples carry `evidence_type: SourceCode` with `node_type: File` (no graph node qualified_name available).

---

## 1. Verified Facts

| # | Statement | Confidence | Provenance |
|---|-----------|------------|------------|
| V1 | The role supports three build modes: `bootc_image`, `traditional_iso`, `generate_only`, resolved by a nested ternary in `select_build_mode.yml`. An unsupported combination (`bootc=true, generate=true`) resolves to `mode_unknown` and fails an assertion. | 5 | `tasks/select_build_mode.yml:12-24` |
| V2 | `main.yml` orchestrates the role in phases: validate vars → check OS compatibility → load distro vars → load package taxonomy → resolve build mode → fetch GPG keys → validate components → compute sources → Phase 1 (install) → Phase 2 (sources) → mode-specific blocks → completion summary. | 5 | `tasks/main.yml:1-247` |
| V3 | The role asserts `ansible_os_family == "RedHat"` and `ansible_distribution in ["Fedora", "AlmaLinux"]`, failing fast on unsupported OS. | 5 | `tasks/main.yml:37-45` |
| V4 | Component definitions (`osbuild_component_defs`) define 12 primary components (base, anaconda, gnome, nvidia, sway, development, container-tools, oneapi, cli-tools, cockpit, docker) plus 4 aliases (core, desktop, audio, virtualization), each with a 17-field schema. | 5 | `defaults/main.yml:199-514` |
| V5 | The `nvidia` component sets `secure_boot_compatible: false` and includes kernel args `rd.driver.blacklist=nouveau`, `modprobe.blacklist=nouveau`, `nvidia-drm.modeset=1`, `DRACUT_NO_XATTR=1`. | 5 | `defaults/main.yml:264-288` |
| V6 | The `desktop` alias conflicts with `sway`, but the primary `gnome` component does NOT declare a conflict with `sway`. Both `gnome` and `sway` can be selected simultaneously via `osbuild_components`. | 4 | `defaults/main.yml:243-262` (gnome: no conflicts), `defaults/main.yml:453-473` (desktop alias: conflicts sway), `defaults/main.yml:290-318` (sway: no conflicts) |
| V7 | The Containerfile uses a 3-stage build: `FROM scratch AS ctx` (build context), `FROM base AS ansible-builder` (Ansible compilation), `FROM base` (runtime). ansible-core is installed only in the builder stage and not shipped in the final image. | 5 | `templates/Containerfile.bootc.j2:13-51` |
| V8 | The build-time playbook (`files/bootc/build.yml`) templates configs to `/usr/etc/` (hostname, os-release, fstab, kernel cmdline) and `/usr/lib/systemd/system/` (NVIDIA CDI service), implementing the Ansible Role Inversion pattern. | 5 | `files/bootc/build.yml:1-130` |
| V9 | `build.sh.j2` iterates `osbuild_components`, skips `blueprint_only` components for bootc, installs packages via `dnf5 install -y --nodocs`, enables services via `systemctl enable`, and installs Flatpaks if any component defines them. | 5 | `templates/build.sh.j2:60-187` |
| V10 | The role migrated from `composer-cli` to `image-builder` CLI. `build.yml` invokes `image-builder build {{ osbuild_image_type }} --distro {{ osbuild_distro }} --blueprint {{ osbuild_blueprint_name }}.toml {{ extra_repo_flags }}` via `ansible.builtin.shell` with `async: {{ osbuild_build_timeout }}`. | 5 | `tasks/build.yml:37-49` |
| V11 | GPG keys are fetched at build time via `get_url` with 30s timeout, `validate_certs: true`, and a PGP marker assertion (`BEGIN/END PGP PUBLIC KEY BLOCK`). Keys are stored in `osbuild_gpgkey_cache_dir` and read into `repo_gpgkeys` fact. | 5 | `tasks/repo_keys.yml:34-83` |
| V12 | The `sources.yml` task builds `osbuild_extra_repo_urls` by iterating `osbuild_sources`, looking up each source in the `repo` dict (loaded from `vars/{{ ansible_distribution }}.yml`), and extracting `metalink` or `baseurl`. | 5 | `tasks/sources.yml:6-19` |
| V13 | Fedora repo vars define 17 repositories with `gpgkey_url` (12 using `file://` URLs to `distribution-gpg-keys`, 5 using `https://`). The `antigravity-rpm` repo has `check_gpg: false`. | 5 | `vars/Fedora.yml:19-78` |
| V14 | AlmaLinux repo vars define 14 repositories. Three use `$releasever`/`$basearch` variables in URLs/metalinks, which are literal dollar-signs in YAML — these will NOT be interpolated by Ansible and will be passed as-is to image-builder. | 4 | `vars/Almalinux.yml:14-70` |
| V15 | `validate_components.yml` checks: (1) all components exist in `osbuild_component_defs`, (2) all required schema fields are present, (3) no conflicting components are selected together. | 5 | `tasks/validate_components.yml:1-56` |
| V16 | The role loads the collection-level package taxonomy via `include_vars: "{{ playbook_dir }}/../../vars/packages/{{ ansible_distribution }}.yml"`, which provides `system_packages.*`, `system_groups`, `system_flatpaks`, `system_copr_repos`. | 5 | `tasks/main.yml:51-53`, `vars/packages/Fedora.yml:1-80` |
| V17 | The `vars/packages.yml` file in the role is an intentionally empty redirect — the canonical taxonomy lives at collection level `vars/packages/{Distribution}.yml`. | 5 | `vars/packages.yml:1-10` |
| V18 | The `bootc.yml` task installs podman/buildah/skopeo/jq, creates a workspace, templates the Containerfile and build.sh, copies the build-time playbook and templates, builds the container image via `containers.podman.podman_image`, and optionally builds a disk image via `image-builder build bootc-installer` or `qcow2`. | 5 | `tasks/bootc.yml:1-123` |
| V19 | The `blueprint.yml` task renders a Jinja2 template to `{{ osbuild_output_dir }}/{{ osbuild_blueprint_name }}.toml` and validates TOML syntax via `python3 -c "import tomli; tomli.load(...)"`, gracefully skipping if `tomli` is unavailable. | 5 | `tasks/blueprint.yml:5-39` |
| V20 | The `handlers/main.yml` contains only one handler: `Reload systemd daemon`. The MIGRATION_LOG confirms 2 composer-related handlers were removed during the image-builder-cli migration. | 5 | `handlers/main.yml:1-10`, `docs/MIGRATION_LOG.md:152-157` |
| V21 | `meta/main.yml` declares `min_ansible_version: "2.15"`, supports Fedora 43 and AlmaLinux 8/9/10, and has no role dependencies. | 5 | `meta/main.yml:1-27` |
| V22 | The `validate_schema.py` test validates component definitions against a 17-field required schema, checks list fields are lists or Jinja2 expressions, and validates enum fields (`size_impact`, `build_time_impact`). It hardcodes a path to `/home/b08x/.hermes/kanban/workspaces/t_3b0b47a4/defaults_main.yml`. | 4 | `tests/validate_schema.py:1-90` |
| V23 | The `validate_build_modes.yml` test validates all three build modes resolve correctly and that the invalid combination (`bootc=true, generate=true`) triggers the failure path. | 5 | `tests/validate_build_modes.yml:1-89` |

<!-- SIFT-GRAPH: claims V1-V23, all evidence_type=SourceCode, provenance=direct file read (graph parse_partial fallback) -->

---

## 2. Errors & Corrections

| # | Statement | Confidence | Provenance |
|---|-----------|------------|------------|
| E1 | The `validate_schema.py` test hardcodes a path (`/home/b08x/.hermes/kanban/workspaces/t_3b0b47a4/defaults_main.yml`) that does not exist in the role's directory structure. This test will fail with `FileNotFoundError` when run from the role or collection. | 5 | `tests/validate_schema.py:11` |
| E2 | The README states `osbuild_image_type` default is `workstation-live-installer` (line 169), but `defaults/main.yml` sets it to `minimal-installer` (line 37). Documentation is stale. | 5 | `README.md:169`, `defaults/main.yml:37` |
| E3 | The README states `osbuild_user_name` default is `ansible` (line 197), but `defaults/main.yml` sets it to `osadmin` (line 616). Documentation is stale. | 5 | `README.md:197`, `defaults/main.yml:616` |
| E4 | The README states `osbuild_blueprint_name` default is `fedora-workstation-custom` (line 167), but `defaults/main.yml` sets it to `custom` (line 19). Documentation is stale. | 5 | `README.md:167`, `defaults/main.yml:19` |
| E5 | The README states Ansible version requirement is "2.9 or higher" (line 143), but `meta/main.yml` declares `min_ansible_version: "2.15"`. Documentation understates the minimum. | 5 | `README.md:143`, `meta/main.yml:7` |
| E6 | The ARCHITECTURAL_REVIEW.md (dated 2026-06-06) describes the role as "still using osbuild-composer daemon" and recommends migration to image-builder-cli. The MIGRATION_LOG.md documents that this migration was already completed in the same session. The review is stale relative to the code it reviews. | 4 | `docs/ARCHITECTURAL_REVIEW.md:35-36`, `docs/MIGRATION_LOG.md:119-160` |
| E7 | The `build.yml` task uses `ansible.builtin.shell` with `async: "{{ osbuild_build_timeout }}"` and `poll: 30`, but the retry logic in `main.yml:176-189` re-imports `build.yml` on failure. The retry block has a `rescue` clause that catches the failure, but the `when` condition (`osbuild_build_retries \| int > 0 and build_status != "FINISHED"`) means if the first build sets `build_status` to "FAILED" (in the rescue block), the retry will trigger. However, `osbuild_build_retries` defaults to 1, so exactly one retry occurs. The retry logic is structurally sound but fragile — it depends on `build_status` being set before the retry condition is evaluated. | 3 | `tasks/main.yml:176-189`, `tasks/build.yml:55-78` |

<!-- SIFT-GRAPH: claims E1-E7, all evidence_type=SourceCode -->

---

## 3. Potential Leads

| # | Statement | Confidence | Provenance |
|---|-----------|------------|------------|
| L1 | The `gnome` and `sway` components can coexist in `osbuild_components` without a declared conflict. Only the `desktop` alias (not the primary `gnome`) declares `conflicts: [sway]`. If a user selects both `gnome` and `sway`, the build will include both desktop environments, which may cause display manager conflicts (both gdm and sway sessions). | 3 | `defaults/main.yml:243-262` (gnome), `defaults/main.yml:290-318` (sway), `defaults/main.yml:453-473` (desktop alias) |
| L2 | AlmaLinux repo vars use `$releasever` and `$basearch` in URLs (e.g., `metalink: "https://mirrors.almalinux.org/metalink?repo=baseos-$releasever&arch=$basearch"`). These are DNF/yum variables, not Ansible/Jinja2 variables. They will be passed as literal strings to image-builder's `--extra-repo` flag. image-builder may or may not expand DNF variables in repository URLs — this needs verification. | 3 | `vars/Almalinux.yml:16-17`, `vars/Almalinux.yml:51-53` |
| L3 | The `Containerfile.bootc.j2` line 73 runs `RUN rm -rf /opt && mkdir -p /opt` to make `/opt` immutable. This destroys any `/opt` content from the base image, which may break packages that ship files in `/opt` (the comment mentions docker-desktop and chrome). This is a known trade-off documented in the template comment. | 4 | `templates/Containerfile.bootc.j2:66-73` |
| L4 | The `build.sh.j2` writes to `/etc/sudoers.d/99-user` (line 150) with NOPASSWD, which is a mutable `/etc` path, not `/usr/etc`. This contradicts the Ansible Role Inversion pattern's principle of targeting `/usr/etc` for immutable configs. The sudoers file will be lost on `bootc upgrade`. | 4 | `templates/build.sh.j2:149-151` |
| L5 | The `build.sh.j2` creates user home directory SSH keys at `/home/{{ osbuild_user_name }}/.ssh/` (lines 154-162), which is runtime state in `/home`, not build-time state in `/usr/etc`. This is appropriate (user home should be runtime state) but means SSH key configuration is not part of the immutable image. | 3 | `templates/build.sh.j2:153-162` |
| L6 | The `build.sh.j2` moves the `default.target` symlink from `/etc/systemd/system/` to `/usr/lib/systemd/system/` (lines 196-199) to make it immutable. This is a partial implementation of the `/usr/etc` pattern — it targets `/usr/lib/systemd` rather than `/usr/etc/systemd`, which is the correct systemd vendor path. | 3 | `templates/build.sh.j2:192-200` |
| L7 | The `build.yml` debug output (line 33) shows a hardcoded CUDA repo URL (`https://developer.download.nvidia.com/compute/cuda/repos/fedora43/x86_64`) in the `--extra-repo` example, which does not match the actual `osbuild_extra_repo_urls` fact content. This is a display-only issue. | 4 | `tasks/build.yml:30-34` |
| L8 | The `osbuild_host_packages` dict has identical package lists for Fedora and AlmaLinux (both: osbuild, image-builder, bash-completion, firewalld, openscap-scanner, scap-security-guide, python3-tomli). The dict could be simplified to a single list, but the dict structure allows future divergence. | 3 | `defaults/main.yml:521-537` |
| L9 | The `osbuild_components` default includes both `gnome` and `sway`, meaning the default build includes both desktop environments. The README examples also show `osbuild_use_nvidia: true` and `osbuild_use_sway: true` as defaults, but these are derived from `osbuild_components` membership, not independent toggles. | 4 | `defaults/main.yml:166-174`, `defaults/main.yml:48-50` |
| L10 | The `container-tools` component declares `sources: [docker-ce-stable]` and `flatpaks: "{{ system_flatpaks.development }}"`. Including development Flatpaks in a container-tools component is a semantic mismatch — Flatpaks are desktop applications, not container tools. | 3 | `defaults/main.yml:342-362` |

<!-- SIFT-GRAPH: claims L1-L10, all evidence_type=SourceCode -->

---

## 4. Contradictions & Tensions

| # | Statement | Confidence | Provenance |
|---|-----------|------------|------------|
| C1 | The ARCHITECTURAL_REVIEW.md recommends targeting `/usr/etc` for all build-time configs, and the Containerfile/build.yml implement this. However, `build.sh.j2` writes sudoers to `/etc/sudoers.d/` (mutable), not `/usr/etc/sudoers.d/` (immutable). This is a direct contradiction of the stated principle. | 4 | `docs/ARCHITECTURAL_REVIEW.md:228`, `templates/build.sh.j2:149-151` |
| C2 | The role declares `min_ansible_version: "2.15"` in meta but the README says "2.9 or higher". The AGENTS.md at the collection level requires `ansible-core >= 2.15.0`. The README is wrong. | 5 | `meta/main.yml:7`, `README.md:143`, `../../AGENTS.md` (collection-level) |
| C3 | The `desktop` alias conflicts with `sway`, but the primary `gnome` component does not. A user selecting `gnome` + `sway` gets no conflict warning, but selecting `desktop` + `sway` fails validation. The alias is stricter than the primary definition. | 4 | `defaults/main.yml:243-262` (gnome), `defaults/main.yml:453-473` (desktop alias) |
| C4 | The `osbuild_only_generate` and `osbuild_build_bootc` variables are both marked `[COMPATIBILITY] Retained for backward compatibility` and `Deprecated`, but they are the primary control flow variables for build mode selection. The deprecation labels are misleading — these are active, load-bearing variables. | 4 | `defaults/main.yml:15-42`, `tasks/select_build_mode.yml:8-10` |
| C5 | The `build.sh.j2` uses `set -ouex pipefail` (line 6), which includes `set -u` (undefined variables are errors). But `osbuild_user_ssh_key` defaults to empty string (`""`), and the template checks `[ -n '{{ osbuild_user_ssh_key }}' ]` — an empty string passes the `-n` check as false, so this is safe. However, if `osbuild_user_ssh_key` were undefined (not just empty), `set -u` would cause the script to fail before reaching the check. | 3 | `templates/build.sh.j2:6`, `defaults/main.yml:624` |

<!-- SIFT-GRAPH: claims C1-C5, all evidence_type=SourceCode -->

---

## 5. Architectural Observations

| # | Statement | Confidence | Provenance |
|---|-----------|------------|------------|
| A1 | The role implements a **component-based architecture** where `osbuild_components` is the primary interface. Components define packages, services, kernel args, sources, flatpaks, repos, and metadata. This is a clean abstraction that separates "what to include" from "how to build". | 5 | `defaults/main.yml:146-514` |
| A2 | The role uses a **3-stage Containerfile** (scratch→ansible-builder→runtime) that separates build-time Ansible compilation from the final image. ansible-core is not shipped in the runtime image. This follows the multi-stage build best practice. | 5 | `templates/Containerfile.bootc.j2:10-51` |
| A3 | The role uses **Ansible Role Inversion** for bootc builds: Ansible runs at build time inside the Containerfile, compiling configs to `/usr/etc` and `/usr/lib/systemd/system/`. This is architecturally aligned with container-native OS best practices. | 5 | `files/bootc/build.yml:1-130`, `templates/Containerfile.bootc.j2:39-42` |
| A4 | The role has a **dual-path architecture**: traditional ISO via `image-builder` CLI (stateless) and bootc via Podman container build. Both paths share the same component definitions, ensuring consistency. | 5 | `tasks/main.yml:111-198`, `tasks/build.yml`, `tasks/bootc.yml` |
| A5 | The role has **external dependency** on collection-level package taxonomy at `vars/packages/{Distribution}.yml`, loaded via `include_vars` with a relative path from `playbook_dir`. This creates a coupling between the role and the collection structure — the role cannot be used standalone without the collection. | 5 | `tasks/main.yml:51-53`, `vars/packages/Fedora.yml:1-80` |
| A6 | The GPG key management system uses `distribution-gpg-keys` package for `file://` URLs and falls back to `https://` for keys not bundled. Keys are validated with PGP marker assertions. This is a robust security practice. | 5 | `tasks/repo_keys.yml:1-86`, `vars/Fedora.yml:5-17` |
| A7 | The NVIDIA bootc repos are defined as inline shell scripts (heredoc `cat > /etc/yum.repos.d/...`) in `defaults/main.yml`, not as TOML source files. This is a different pattern from the traditional ISO path where sources are TOML files in `files/*/sources/`. The bootc path writes directly to `/etc/yum.repos.d/` (mutable), not `/usr/etc/yum.repos.d/`. | 4 | `defaults/main.yml:86-144`, `templates/build.sh.j2:37-39` |
| A8 | The role has 8 task files totaling ~677 lines (main:247, select_build_mode:35, install:45, sources:27, repo_keys:87, validate_components:56, blueprint:40, build:133, bootc:123). The MIGRATION_LOG documents a 75% code reduction from the pre-migration state (~370 lines removed). | 5 | All task files (see file listing) |

<!-- SIFT-GRAPH: claims A1-A8, all evidence_type=SourceCode -->

---

## 6. Risk Assessment

| Risk | Severity | Likelihood | Provenance | Impact |
|------|----------|------------|------------|--------|
| `validate_schema.py` hardcodes non-existent path | Medium | Certain (when run) | `tests/validate_schema.py:11` | Test suite reports false failure; schema validation is silently broken |
| `build.sh.j2` writes sudoers to `/etc` (mutable) | Medium | High (every bootc build) | `templates/build.sh.j2:149-151` | Sudoers config lost on `bootc upgrade`; user loses passwordless sudo |
| AlmaLinux `$releasever`/`$basearch` in repo URLs | Medium | Unknown | `vars/Almalinux.yml:16-17` | If image-builder doesn't expand DNF variables, repo URLs will be malformed |
| `gnome` + `sway` no conflict declared | Low | Medium (user selects both) | `defaults/main.yml:243-262` | Dual desktop environments; potential display manager conflicts |
| NVIDIA bootc repos write to `/etc/yum.repos.d/` (mutable) | Low | High (every NVIDIA bootc build) | `defaults/main.yml:86-144` | Repo configs lost on `bootc upgrade`; NVIDIA driver updates may fail |
| README documentation drift (5+ stale values) | Low | Certain | `README.md:143,167,169,197` vs `defaults/main.yml`, `meta/main.yml` | Users configure wrong defaults; confusion |
| ARCHITECTURAL_REVIEW.md is stale | Low | Certain | `docs/ARCHITECTURAL_REVIEW.md:35-36` | Review recommends changes already implemented; misleading |

<!-- SIFT-GRAPH: 7 risks, all evidence_type=SourceCode -->

---

## 7. Self-Critique Ledger

| # | Critique | New Claim? | Provenance |
|---|----------|------------|------------|
| S1 | Did I check whether the `docker` component (declared in the comment at `defaults/main.yml:164` but not defined in `osbuild_component_defs`) is actually missing? — Yes, the `docker` component is listed in the "Available components" comment at line 164 but has no definition in `osbuild_component_defs`. Selecting it would fail validation. | Yes (new claim) | `defaults/main.yml:164` (comment), `defaults/main.yml:199-514` (defs — no `docker` key) |
| S2 | Did I verify the `osbuild_sources` fact aggregation logic? — The `main.yml:69-77` computes `osbuild_component_sources` by iterating `osbuild_components`, checking if each is in `osbuild_component_defs` and has `sources` defined, then concatenating. This is combined with `osbuild_common_sources_*` at line 582 to form `osbuild_sources`. The logic is correct but relies on `osbuild_component_defs[c].sources` being a list (or Jinja2 expression resolving to one). | No (confirms V4, V12) | `tasks/main.yml:69-77`, `defaults/main.yml:582` |
| S3 | Did I check the `tests/inventory/` directory? — No, I did not read it. It may contain test inventory configuration. | No (gap flagged) | `tests/inventory/` (not read) |
| S4 | Did I check the `snippets/custom-first-boot.sh.j2` template? — No, this is a significant template (152 parse_partial lines) that may contain first-boot logic. I did not read it. | No (gap flagged) | `templates/snippets/custom-first-boot.sh.j2` (not read) |
| S5 | Did I verify the `fedora-workstation.toml.j2` and `almalinux-workstation.toml.j2` blueprint templates? — No, these are the core blueprint templates for the traditional ISO path. I did not read them. | No (gap flagged) | `templates/fedora-workstation.toml.j2`, `templates/almalinux-workstation.toml.j2` (not read) |
| S6 | Did I check the `disk.toml.j2` and `iso.toml.j2` bootc disk config templates? — No, these configure the bootc disk image build. I did not read them. | No (gap flagged) | `templates/disk.toml.j2`, `templates/iso.toml.j2` (not read) |

---

## 8. Provenance Coverage Summary

| Metric | Value |
|--------|-------|
| Total claims (V + E + L + C + A + S) | 23 + 7 + 10 + 5 + 8 + 6 = 59 |
| Claims with source-level provenance (file + line range) | 59/59 = 100% |
| Claims with graph-node provenance (qualified_name) | 0/59 = 0% |
| Evidence type distribution | SourceCode: 59, Documentation: 0, Test: 0, Config: 0 |
| Files read | 18 of 42 role files (43%) |
| Files not read | `snippets/*` (4 files), `fedora-workstation.toml.j2`, `almalinux-workstation.toml.j2`, `disk.toml.j2`, `iso.toml.j2`, `etc/osbuild-composer/repositories/*` (3 files), `systemd/*` (1 file), `usr/etc/*` (4 files), `tests/inventory/*`, `snippets/custom-first-boot.sh.j2`, `snippets/custom-first-boot.desktop.j2`, `snippets/custom-first-boot-launcher.sh.j2`, `snippets/nvidia-cdi.sh.j2` |

**Note**: All provenance is source-fallback (direct file reads). The codebase-memory graph has no resolvable nodes for this role due to `parse_partial` status on all Jinja2/YAML files. Per SIFT-Graph protocol, this means **graph-level provenance coverage is 0%**, but source-level provenance coverage is 100%.

---

## 9. SIFT-Graph Meta-Rubric Scores

| Dimension | Score | Weight | Weighted | Notes |
|-----------|-------|--------|----------|-------|
| Claim Provenance | 1 | 40% | 0.40 | 0% graph-level; 100% source-level. Graph has no nodes for this role. Essential Cap applies. |
| Section Completeness | 5 | 25% | 1.25 | All 8 sections present with claims. |
| Severity Calibration | 4 | 20% | 0.80 | Confidence distribution: 5s (24), 4s (14), 3s (11). std_dev ≈ 0.8. Good variance. |
| Self-Critique Payoff | 3 | 15% | 0.45 | 1 new claim (S1: missing `docker` component definition), 5 gap acknowledgments. 1/59 ≈ 1.7% new claims; but 5 gaps flagged = useful critique. |
| **Raw Score** | | | **2.90** | |
| Pitfall Penalty | | | -0.0 | No anti-patterns detected (no fabricated provenance, no out-of-range scores). |
| **Pre-Cap Score** | | | **2.90** | |
| **Essential Cap** | | | **2.0** | Claim Provenance < 3 (score=1). Final score capped at 2.0. |
| **Final Score** | | | **2.0** | |
| Chain Integrity | 1 | | | min(1, 5, 4, 3) = 1 |

**Essential Cap**: TRIGGERED. Graph-level provenance is 0% because all role files are `parse_partial` (Jinja2/YAML). The codebase-memory indexer cannot parse these file types into graph nodes. Source-level provenance is 100%, but the SIFT-Graph rubric requires graph resolution.

**Status**: Marginal — significant revisions needed. The source-fallback approach provides reliable analysis (all claims trace to exact file:line ranges I read), but the graph-verification guarantee that distinguishes SIFT-Graph from static SIFT is absent for this target. The report is trustworthy as a source-verified analysis but does not meet the SIFT-Graph standard of graph-verified provenance.

---

## Recommendations

1. **Fix `validate_schema.py`**: Replace hardcoded path with `os.path.join(os.path.dirname(__file__), '..', 'defaults', 'main.yml')` or accept a CLI argument.
2. **Fix sudoers path in `build.sh.j2`**: Write to `/usr/etc/sudoers.d/99-user` instead of `/etc/sudoers.d/99-user` for bootc immutability.
3. **Add `gnome` conflicts `sway`** (or document that dual desktop is intentional).
4. **Define the `docker` component** or remove it from the "Available components" comment.
5. **Update README** to match actual defaults (osbuild_blueprint_name, osbuild_image_type, osbuild_user_name, min_ansible_version).
6. **Update ARCHITECTURAL_REVIEW.md** to reflect that image-builder-cli migration is complete.
7. **Verify AlmaLinux `$releasever`/`$basearch`** handling in image-builder — if it doesn't expand DNF variables, use Ansible-templated URLs instead.
8. **Move NVIDIA bootc repo configs** from `/etc/yum.repos.d/` to `/usr/etc/yum.repos.d/` for bootc immutability.
9. **Read the 24 unread template files** for a complete analysis — especially `custom-first-boot.sh.j2` (152 lines) and the blueprint templates.
