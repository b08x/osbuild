# Plan: component-files-only-tracker

Facts: [facts.md](facts.md) (32 accepted). Fact IDs are cited per step.

## Approach

Component files (`roles/osbuild/files/<distro>/<major>/<arch>/components/*.yml`) plus one frame per image kind become the only source of package data. Every consumer of `osbuild_components` / `osbuild_component_defs` (validation, sources, `blueprint.toml.j2`, `build.sh.j2`, `Containerfile.bootc.j2`, `files/bootc/build.yml`) is either deleted or switched to the already-loaded `_osbuild_bp_components` dict and `osbuild_blueprint_components`. The static workstation TOMLs for AlmaLinux 10, Rocky 9 and Fedora 43 are split into frame + components, using a set-equality parity check. `scripts/package_tracker.py` is rewritten around a `ComponentStore` (one per target dir) and drops the taxonomy code.

A small render harness (`tests/render_blueprint.yml`, localhost, no image build) runs `tasks/components.yml` + `blueprint-components.toml.j2` for any target/component list. Snapshot and parity checks (facts 9, 14, 15) use it, so they need no build host, sudo or network.

## Steps

### 0. Baseline snapshot (before any change)
- Add `tests/render_blueprint.yml`: `hosts: localhost`, `connection: local`, `gather_facts: false`. It sets `osbuild_distro`, `osbuild_arch` and `osbuild_blueprint_components` from `-e`, then `include_role: osbuild, tasks_from: components.yml` and templates `blueprint-components.toml.j2` to `$OUT`. If `include_role` pulls defaults that need facts, use `vars_files: roles/osbuild/defaults/main.yml` + `import_tasks` instead.
- Render the three existing component playbooks' lists (rocky-iso, rocky-iso-nvidia, rocky-iso-intel-oneapi) into `goals/component-files-only-tracker/baseline/*.toml`.
- Add `tests/blueprint_packages.py`: parses a blueprint TOML (`tomllib`), handles both `packages = [...]` and `[[packages]]` forms plus `[[groups]]`, and prints the sorted name set. Record baseline sets for the static TOMLs being split (alma 10 ×2, rocky 9 ×2, fedora 43 ×2, rocky 10 cuda container) in `baseline/*.pkgs`.
- **Verify:** baseline files exist; the harness renders the rocky-iso list without error.

### 1. Extend the component schema (facts 6, 7)
- `roles/osbuild/defaults/main.yml`: replace the legacy "Component Definitions" schema comment with the component-file schema: `label`, `packages`, `services`, `kernel_args`, `repo_urls`, `fragment`, plus the new optional `flatpaks`, `bootc_repos` and `copr_repos`.
- `tasks/components.yml`: also derive `_osbuild_bp_flatpaks`, `_osbuild_bp_bootc_repos` and `_osbuild_bp_copr_repos` (flatten, unique).
- **Verify:** the harness still renders identical output to baseline (`diff`).

### 2. Port bootc to component files (fact 7)
- `templates/build.sh.j2`: loop over `osbuild_blueprint_components` / `_osbuild_bp_components`, use the new `_osbuild_bp_*` lists, and drop the `blueprint_only` and "string instead of list" branches. Delete the header `# Components:` line, or switch it to `osbuild_blueprint_components`.
- `templates/Containerfile.bootc.j2`: pass `osbuild_blueprint_components` (not the defs) in `-e`.
- `files/bootc/build.yml`: change `'nvidia' in osbuild_components` to `'nvidia' in osbuild_blueprint_components` (2 places).
- `tasks/main.yml`: make sure `components.yml` runs before `bootc.yml` in bootc mode (it is currently gated on a non-empty list; bootc then requires a non-empty list, so add an assert in bootc mode).
- **Verify:** `ansible-playbook --syntax-check`; render `build.sh.j2` and `Containerfile.bootc.j2` through the harness for the rocky nvidia list, and check with grep that dnf5 install lines and the nvidia `when` resolve.

### 3. Remove the legacy vars, template mode and taxonomy (facts 1–5)
- Delete `tasks/validate_components.yml` and its import, the `osbuild_component_sources` set_fact, and the "Load package taxonomy" task in `tasks/main.yml`.
- `defaults/main.yml`: delete `osbuild_components`, `osbuild_component_defs`, `osbuild_use_blueprint_template` and `osbuild_blueprint_template`. Change `osbuild_sources` to drop `+ osbuild_component_sources`, and update its comment.
- `tasks/blueprint.yml`: remove the template branch. Modes are components or static.
- Delete `templates/blueprint.toml.j2`, `vars/packages/{Fedora,AlmaLinux,Rocky}.yml` (keep `00-distributions.yml` if anything else loads it; check with grep) and `roles/osbuild/vars/packages.yml`.
- `roles/osbuild/tests/validate_schema.py`: rewrite to validate component files (label + non-empty packages + known keys), or delete it if it duplicates the `components.yml` assert. Update `validate_build_modes.yml` if it toggles template mode.
- `tasks/main.yml:23`: change the debug line to print `osbuild_blueprint_components`.
- **Verify:** `grep -rnE 'osbuild_components\b|osbuild_component_defs|osbuild_component_sources|system_packages|system_groups|osbuild_use_blueprint_template|osbuild_blueprint_template\b|blueprint\.toml\.j2' roles playbooks osbuild.yml` returns nothing; harness output still equals baseline.

### 4. Split static blueprints into frame + components (facts 8, 9, 10)
For each of `almalinux/10`, `rocky/9`, `fedora/43` (x86_64):
- `frames/workstation.toml`: the non-composable sections of the plain TOML (installer modules, firewall, timezone, locale, `[[customizations.files]]` dnf.conf, `[[customizations.repositories]]`). Use `files/rocky/10/x86_64/frames/workstation.toml` as the model. NVIDIA-only files and repos go to the nvidia component's `fragment`.
- `components/*.yml`: mirror the rocky/10 component names (base, anaconda, gnome-desktop, fonts, audio, multimedia, google-chrome, vscode, development, containers-virt, cockpit, nvidia, …) and assign each static package to exactly one component. Services and kernel append come from the TOML's `[customizations.services]` / `[customizations.kernel]`. `repo_urls` come from the TOML repositories plus that distro's `sources/*.toml` URLs, since depsolve repos no longer come from `osbuild_component_sources`.
- Components exist only where the distro has the packages (e.g. no intel-graphics if absent).
- Parity: render `plain` and `nvidia` component lists through the harness, then `tests/blueprint_packages.py` set == baseline set for that TOML. Write the check as `tests/test_component_parity.py`, which reads a table of (target, component list, baseline file) entries.
- Delete the six split TOMLs. **Open:** `fedora-workstation-43-igx.toml` and `-intel-oneapi.toml` are referenced by no playbook. The plan leaves them in place (not split, so fact 10 does not cover them) and flags them for the user.
- **Verify:** `pytest tests/test_component_parity.py`; `ls` shows the components and frames dirs for all four targets.

### 5. Container frame + cuda-container component (fact 14)
- `files/rocky/10/x86_64/frames/container.toml`: the `[[customizations.files]]` of `rocky-10-2-cuda-container.toml`. `components/cuda-container.yml` holds its 5 packages and the repo_urls for the CUDA repo.
- Risk: `blueprint-components.toml.j2` always writes `[customizations] hostname`; the `container` image type may reject it. If image-builder rejects it, guard hostname with a frame-level flag, or emit it only when `osbuild_image_type != 'container'`.
- Playbook: `osbuild_blueprint_components: [cuda-container]`, `osbuild_blueprint_frame_path: …/frames/container.toml`; drop `osbuild_static_blueprint_path` and `osbuild_use_blueprint_template`.
- Delete `container/rocky-10-2-cuda-container.toml`.
- **Verify:** parity row in `tests/test_component_parity.py`.

### 6. Playbooks (facts 11, 12, 13, 16)
- Delete `playbooks/osbuild-rocky-iso.yml`, `-nvidia.yml`, `-nvidia-generate.yml` and `-nvidia-interactive.yml`. First check with grep for references in README, the skill and Makefile/scripts, and repoint them to the `*-components.yml` playbooks.
- `osbuild-almalinux-iso.yml` / `-nvidia.yml`: switch to `osbuild_blueprint_components` (plain / nvidia lists from step 4) and drop the static path, template flag and `osbuild_components`.
- `*-components.yml` (3 files): delete the legacy `osbuild_components` block and its comment.
- `osbuild.yml` and `playbooks/osbuild.yml` (identical copies): replace `osbuild_components` with a per-distro map, `osbuild_blueprint_components_default: {Fedora: [...], AlmaLinux: [...], Rocky: [...]}`, keyed by `ansible_distribution`. Rocky 9 vs 10 component names must exist in both dirs; if they differ, key by `ansible_distribution ~ ansible_distribution_major_version`.
- Optionally drop `osbuild_static_blueprint_path` from defaults once no playbook uses it. Keep the static mode itself (not in the facts).
- **Verify:** `for p in osbuild.yml playbooks/*.yml; do ansible-playbook --syntax-check "$p"; done`; render the almalinux and osbuild.yml lists for each distro through the harness.

### 7. Snapshot check (fact 15)
- `tests/test_component_parity.py` also diffs the harness output for the three `*-components.yml` lists against `baseline/*.toml` byte for byte.
- **Verify:** `pytest tests/test_component_parity.py`.

### 8. Rewrite package_tracker.py (facts 17–25)
- Remove `TaxonomyManager`, `cli_build_manifest`, `tui_select_build_packages`, the `build` subparser and every `vars/packages` path.
- `discover_targets(root) -> {"rocky/10/x86_64": Path, …}` (glob `roles/osbuild/files/*/*/*/components`).
- `ComponentStore(dir)`: `components()` (name → ruamel CommentedMap, loaded with round-trip `YAML()`, `preserve_quotes`, same indent as the existing files), `add(comp, pkgs, force)`, `remove(comp, pkgs)`, `find(pkg)`, `save(comp)`. Add appends in place; existing order and comments are kept. Remove refuses to empty `packages`. Duplicates across components return a conflict list; CLI requires `--force`.
- `RepoVerifier`: change `REPO_PROFILES` to be keyed by target (`rocky/10`, `rocky/9`, `almalinux/10`, `fedora/43`), or build the repo list from the target's base repos + the union of components' `repo_urls`. Keep the `@` skip and the error semantics.
- CLI: `list --target T`, `search NAME [--target T]`, `add --target T COMPONENT PKG... [--verify] [--force]`, `remove --target T COMPONENT PKG...`, `tui`. A missing `--target` exits 2 with the available targets listed (fact 18).
- TUI (facts 26–30): main loop with target select (skipped when one target) → component list (`label (n)` + Back) → submenu `Edit packages | Add packages | Show details | Back`. Edit = `questionary.checkbox` with all items checked; diff → confirm listing removals → `remove`. Add = text input → optional verify → duplicate confirm → `add`. Details = rich panel of label, repo_urls, services, kernel_args, fragment.
- **Verify:** step 9 tests; `python3 scripts/package_tracker.py list --target rocky/10/x86_64` against the real tree; a manual TUI walkthrough for facts 26–30.

### 9. Tracker tests (fact 31)
- Rewrite `tests/test_package_tracker.py`: keep the RepoVerifier tests (adjust to target keys). Add fixture tests using `tempfile` component dirs with comments: list counts, search hits across targets, add appends and keeps comments (compare raw text), add no-op on an existing package, duplicate refused without `--force`, remove keeps comments, remove-last refused, missing `--target` exit code, `@group` skips verify.
- **Verify:** `python3 -m pytest tests/ -q`.

### 10. Docs (fact 32)
- `README.md`, `roles/osbuild/README.md`, `.claude/skills/syncopated/SKILL.md` and `.agents/skills/syncopated/SKILL.md`: remove the legacy var, taxonomy and template-mode text, and document the component-file schema, the four targets and the new tracker commands. Leave `roles/osbuild/.zread/` (generated snapshots) and `docs/ARCHITECTURAL_REVIEW.md` / `sift-graph-osbuild-report.md` (historical reports) alone.
- **Verify:** `grep -nE 'osbuild_components\b|osbuild_component_defs|vars/packages' README.md roles/osbuild/README.md .claude/skills/syncopated/SKILL.md .agents/skills/syncopated/SKILL.md` returns nothing.

## Final verification
```bash
grep -rnE 'osbuild_components\b|osbuild_component_defs|system_packages|vars/packages' roles playbooks osbuild.yml   # empty
for p in osbuild.yml playbooks/*.yml; do ansible-playbook --syntax-check "$p" || exit 1; done
python3 -m pytest tests/ -q
```

## Risks / open questions
- **Splitting by hand is the largest effort:** about 1,500 package entries across six TOMLs. Set-equality parity is the guard; the assignment of packages to components is a judgment call, and rocky/10's assignments are the model.
- **Depsolve repos:** removing `osbuild_component_sources` changes `osbuild_sources` (`--extra-repo`) for every build. Component `repo_urls` must cover what the static builds got from `osbuild_sources`. Generate-only output does not show depsolve failures; a real build on tinybot is the user's hand-off check.
- **Container image type + hostname**, step 5.
- **Fedora igx / intel-oneapi TOMLs** are unreferenced and left in place; the user decides later.
- **bootc base image** in `osbuild.yml` is Fedora 43 regardless of host; bootc on Rocky/Alma hosts would use Fedora component names. That is existing behavior and not changed here.
- **`render_blueprint.yml` harness:** role defaults reference facts (`ansible_distribution`); the harness must set the variables that derive from facts, or gather facts on localhost.
