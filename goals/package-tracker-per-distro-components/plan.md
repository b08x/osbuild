# Plan: per-distro component files and the package_tracker refactor

Repos: `IO` = `~/WorkspaceV3/Syncopated/infra.osbuild` (branch `feature/image-builder-merge`),
`OB` = `~/WorkspaceV3/Syncopated/osbuild` (branch `feature/consume-infra-osbuild`).
Scratch (baselines, snapshots) goes under the session scratchpad, not in either repo, except the parity test (Step 9).

## Solution approach

Components become the only package data. Each `vars/<distro>/<ver>/components/<name>.yml` is the old
`image_builder_component_defs` entry for that name (catalog fields as optional keys), so one file format serves both the
template path (`image_builder_components`) and the file-composed path (`image_builder_blueprint_components`).
A loader task builds `image_builder_component_defs` at run time from those files. The taxonomy
(`vars/packages/<Distro>.yml`) is converted once by a script, then deleted. `package_tracker.py` is rewritten to
read/write component files, addressed as `--distro <name>-<ver>` plus `--component`.

Order matters: capture a baseline of the **current** catalog first (Step 1); every later step is checked against it.

## Steps

### 1. Baseline snapshot (no repo changes)
- Write a throwaway playbook in the scratchpad: `hosts: localhost`, `vars_files: [defaults/main.yml, vars/packages/<Distro>.yml]` (plus the vars the defaults template needs, e.g. `image_builder_distro`), then `copy: content={{ image_builder_component_defs | to_nice_json }}`.
- Run it for `fedora-43`, `almalinux-9.8`, `almalinux-10.2`, `rocky-9.8`, `rocky-10.2` and store `baseline/<distro>-<ver>.json`.
- Also snapshot `files/rocky/10/x86_64/{components,frames}` (checksums) for fact 3.
- Files: none in the repos. Verify: five JSON files exist, each with the same key set as `defaults/main.yml:207-550` (about 16 entries).

### 2. Move rocky/10 components and frames (IO)
- `git mv roles/image_builder/files/rocky/10/x86_64/{components,frames} roles/image_builder/vars/rocky/10/` (drop the `x86_64` level; the `files/` `workstation/` static blueprints and other `files/` content stay).
- Files: `roles/image_builder/files/rocky/10/x86_64/{components,frames}/**`.
- Verify: `git diff -M --stat` shows only renames; checksums equal the Step 1 snapshot; `find roles/image_builder/files -name components -o -name frames` is empty (fact 1, 3).

### 3. Path resolution and loader task (IO)
- `defaults/main.yml:659-663`: `image_builder_components_dir` and `image_builder_blueprint_frame_path` become `{{ role_path }}/vars/<distro>/<major>/{components,frames/workstation.toml}`. Still overridable (fact 8, 25).
- `tasks/components.yml:11` and `templates/blueprint-components.toml.j2:33`: they use `lookup('ansible.builtin.file', image_builder_components_dir ~ ...)`, which searches `files/`; switch to absolute `role_path` paths (fact 25). Check the frame-path consumer in `tasks/blueprint.yml` too.
- New `tasks/load_components.yml`, imported from `tasks/main.yml` replacing the "Load package taxonomy" include_vars at line 71-77: `find` `*.yml` in the components dir, `slurp`/`from_yaml` each, merge into `image_builder_component_defs` with per-key defaults (the former catalog defaults), then `combine` with any playbook-supplied `image_builder_component_defs` so overrides win (fact 6, 23).
- Keep `vars/{Fedora,Rocky,AlmaLinux}.yml` (repo vars) as is. Load `vars/<distro>/<ver>/main.yml` and `vars/distributions.yml` via `include_vars`.
- Files: `defaults/main.yml`, `tasks/main.yml`, new `tasks/load_components.yml`, `tasks/components.yml`, `templates/blueprint-components.toml.j2`, `tasks/blueprint.yml`.
- Verify: `ansible-playbook --syntax-check` on a stub; ansible-lint on the role.

### 4. Taxonomy → component conversion script (scratchpad, then discarded)
- For each of `fedora-43`, `almalinux-{9,10}`, `rocky-9`, and the missing names for `rocky-10`: take the Step 1 baseline JSON for that distro (not the raw taxonomy) and emit one `<name>.yml` per catalog entry, keeping every key. This is what makes the parity check exact.
- The six unreferenced subcategories (`AudioVideo.alsa`, `AudioVideo.pulseaudio`, `Graphics.intel`, `System.gui_toolkit`, `Utility.browsers`, `Utility.extra`) become extra components `alsa`, `pulseaudio`, `intel-graphics`, `gui-toolkit`, `browsers`, `extra` (reuse the `rocky/10` names where they exist, and do not overwrite `rocky/10` files).
- Header on each generated file: `Seeded from vars/packages/<Distro>.yml on <date>; not repodata-verified.` Existing `rocky/10` files keep their verified headers.
- Rocky 9 and AlmaLinux 9/10 `repo_urls`/frames: copy `rocky/10/frames/workstation.toml` only if a matching static frame exists today; otherwise omit (frames are used only by file-composed builds, which exist only for Rocky 10). Open question 1.
- Distro-level leftovers go to `vars/<distro>/<ver>/main.yml`: `image_builder_build_host_packages`, `image_builder_legacy`, and any flatpak/COPR entries not referenced by a catalog entry. `00-distributions.yml` → `vars/distributions.yml` (`git mv`).
- Files: `roles/image_builder/vars/{fedora/43,almalinux/{9,10},rocky/{9,10}}/{components,frames?}/*`, `.../main.yml`, `vars/distributions.yml`.
- Verify: directories exist (fact 2); the six extra components are present (fact 4).

### 5. Remove the catalog and taxonomy from the role (IO)
- Delete `image_builder_component_defs` (`defaults/main.yml:207-550`) and `vars/packages/*.yml`; fix README rows (`README.md:35`) and the comments at `defaults/main.yml:15` and `:640-660`.
- Update `tests/integration/targets/role_image_builder/tasks/generate_only.yml:19` (uses `image_builder_system_packages`) to read the loaded catalog.
- Verify: `grep -rn "image_builder_system_packages\|vars/packages" IO OB` returns nothing (fact 5); `ansible-lint`, `yamllint` clean.

### 6. Parity test (IO)
- Add `tests/unit/roles/test_component_parity.py` (or a script under `tests/` driven by the integration target) that runs the loader for each distro/version and compares to the committed baselines under `tests/fixtures/component_defs/<distro>-<ver>.json` (copied from Step 1). Whole entries are compared (every key), not only `packages` (fact 9, 24).
- Also assert the `rocky/10` components equal their Step 2 checksums (fact 3).
- Verify: `/tmp/claude-1000/runtest.sh` units; expect 0 differences.
- **Intended differences for Rocky 10**:
  - The 16 pre-existing Rocky 10 component files (`anaconda`, `audio`, `base`, `cockpit`, `development`, `nvidia`, `selection-extras`, `vscode`, `intel-oneapi`, `fonts`, `gnome-desktop`, `google-chrome`, `gui-toolkit`, `intel-graphics`, `multimedia`, `containers-virt`) moved from `files/rocky/10/x86_64/` retain their exact pre-migration SHA256 checksums and verified package definitions. They diverge intentionally from the former `defaults/main.yml` generic EL catalog where packages had already been verified against Rocky 10 repodata.
  - The remaining Rocky 10 components (`alsa`, `pulseaudio`, `browsers`, `cli-extra`, `cli-tools`, `communication`, `container-tools`, `core`, `creative-media`, `desktop`, `desktop-apps`, `engineering-cad`, `extra`, `gnome`, `oneapi`, `reverse-engineering`, `scientific`, `sway`, `virtualization`) were seeded from the taxonomy with repodata-sanitized packages.
  - Rocky 10 retains `frames/workstation.toml` for file-composed blueprint builds; other distros use blueprint templates.

### 7. Changelog and docs (IO)
- Amend the existing merge fragment under `changelogs/fragments/` (no new "breaking" fragment, `galaxy.yml` stays 2.4.0, fact 21). Update `roles/image_builder/README.md` for the new layout and the optional component keys (fact 23).

### 8. package_tracker.py rewrite (OB)
- `resolve_taxonomy_dir` → `resolve_vars_dir` (same lookup order: `--vars-dir` / `$INFRA_OSBUILD_PATH` / sibling checkout, still rejecting the installed `collections/` copy), pointing at `roles/image_builder/vars`. Keep `--taxonomy-dir` as a hidden alias for one release? No: clean break, drop it.
- `TaxonomyManager` → `ComponentManager`: load `vars/<distro>/<ver>/components/*.yml` with ruamel round-trip so header comments and key order survive (fact 17); `distributions_map`/mappings from `vars/distributions.yml`.
- `--distro <name>-<ver>` parser: `fedora` → `fedora-43`; a bare name with several versions errors listing choices; `All` fans out (facts 10, 12).
- Commands: `add`/`remove` with `--component`, `add --create --label` (facts 11), `--repo-url/--service/--kernel-arg` (13); `list` with package counts, `verify` with each target's `repo_urls` (14); `build-manifest --components` writes `image_builder_blueprint_components` and `image_builder_distro` (15); TUI distro → version → component picker (16).
- Replace the module constant `TAXONOMY_SUBPATH`, `DISTROS` etc.
- Files: `scripts/package_tracker.py`; update `README.md`, both `SKILL.md` files for the new commands.
- Verify: see Step 9.

### 9. Tracker tests (OB)
- Rewrite `tests/test_package_tracker.py` (163 lines): fixtures copy a small vars tree into `tmp_path`; cover add/remove/verify, `--create` needs `--label`, `All` fan-out with name mapping, ambiguity error, comment preservation (diff only the changed lines), `build-manifest --components` (facts 10-15, 17, 18).
- Verify: `pytest -q` in OB.

### 10. osbuild consumer updates (OB)
- Update the four component playbooks (`playbooks/osbuild-rocky-iso-{,intel-oneapi-,nvidia-}components.yml`, `osbuild-rocky-iso-nvidia-components.yml`): header comments pointing at the old `files/.../components/` path, and any `image_builder_system_packages` use.
- Update the three `build-selections/*.yaml` manifests and the `package_tracker.py` manifest output (`selected_components` → `image_builder_blueprint_components`).
- Reinstall the collection from IO (`ansible-galaxy collection install ../infra.osbuild --force --no-deps`).
- Verify: `ansible-playbook --syntax-check` on all 13 playbooks; `pytest`; no `files/rocky/10/x86_64/components` strings left (fact 20).

### 11. Gates in IO (fact 19)
- `/tmp/claude-1000/runtest.sh`: `ansible-test sanity`, `units`, ansible-lint, yamllint, and `ansible-test integration role_image_builder --allow-destructive --allow-root`.

### 12. Hand-off (fact 22)
- Append to this plan the exact commands for you to run on tinybot (rocky-10 components playbooks; one Fedora, one AlmaLinux 10 build; EL9 builds after VMs exist). I do not run them.

#### Tinybot Run Commands

Run these on the `tinybot` build host (or target tinybot from inventory):

1. **Rocky 10 Component Blueprint Generation:**
   ```bash
   ansible-playbook playbooks/osbuild-rocky-iso-components.yml
   ansible-playbook playbooks/osbuild-rocky-iso-nvidia-components.yml
   ansible-playbook playbooks/osbuild-rocky-iso-intel-oneapi-components.yml
   ```

2. **Execute Rocky 10 Image Builds on Tinybot:**
   ```bash
   bash /var/tmp/osbuild-images/build-rocky-10-2-workstation-components.sh
   bash /var/tmp/osbuild-images/build-rocky-10-2-workstation-nvidia-components.sh
   bash /var/tmp/osbuild-images/build-rocky-10-2-workstation-intel-oneapi-components.sh
   ```

3. **Fedora 43 Workstation Build:**
   ```bash
   ansible-playbook playbooks/osbuild.yml -e image_builder_distro=fedora-43 -e image_builder_only_generate=false
   ```

4. **AlmaLinux 10 Workstation Build:**
   ```bash
   ansible-playbook playbooks/osbuild-almalinux-iso.yml
   bash /var/tmp/osbuild-images/build-almalinux-10-2-workstation.sh
   ```

5. **EL9 Builds (after VMs exist):**
   ```bash
   ansible-playbook playbooks/osbuild.yml -e image_builder_distro=rocky-9.8 -e image_builder_only_generate=false
   ansible-playbook playbooks/osbuild.yml -e image_builder_distro=almalinux-9.8 -e image_builder_only_generate=false
   ```


## Risks and open questions

1. **Frames for the other distros.** Only Rocky 10 has file-composed builds and a frame today. The plan generates frames only where one exists; confirm that is acceptable (EL9/Fedora have none to migrate).
2. **Seeded components are unverified.** The Rocky 9, AlmaLinux 9/10 and Fedora components are copies of the taxonomy data. `verify` against repos is available but not part of the done condition.
3. **Fedora older than 43.** `fedora-42` and `fedora-44` have no directory; the path resolver errors for them. Say so in the README.
4. **Loader cost and ordering.** Loading about 20 files per run via `slurp` is cheap, but `image_builder_component_defs` must exist before `validate_components.yml` runs. Step 3 places the loader before it.
5. **Fixtures lock the catalog.** The parity fixtures will fail on every intended catalog edit afterwards. Treat them as migration evidence and delete them after the tinybot runs succeed.
6. **Hidden consumers.** The bootc Containerfile passes a filtered `image_builder_component_defs` JSON to a nested ansible run; confirm in Step 5 that this path still gets the loaded catalog.
7. **EL10 host quirks from the previous goal** (`role_builder` not runnable on EL10, un-run Rocky/Alma VMs) are unchanged and out of scope.
