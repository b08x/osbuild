---
name: syncopated
description: Builder agent for custom OS appliances and container images. Generates an osbuild-role playbook (plus a static blueprint or blueprint components when needed) that writes a blueprint and build-<name>.sh, then verifies both without building.
---

# Syncopated Appliance Builder Skill

Turn a natural-language appliance request into a playbook for the `osbuild`
role (`roles/osbuild/`), verified to the point where the user only has to run
the generated build script.

Repository facts:

- Standalone repo: `ansible.cfg` sets `roles_path = ./roles` and
  `inventory = ./inventory/hosts.yml`. Group `builder` = `gir` (Fedora 43,
  local connection) and `tinybot` (AlmaLinux 10).
- `roles/composer_cli/` (`composer_cli.yml`) is the osbuild-composer/Weldr
  alternative. This skill targets `roles/osbuild/` only.
- Package taxonomy: `vars/packages/<Fedora|Rocky|AlmaLinux>.yml`, loaded for
  the *target* distro (`osbuild_target_distribution`, derived from
  `osbuild_distro`). Edit it with `scripts/package_tracker.py`
  (`list|search|add|remove|build`). Manifests in `build-selections/` are not
  read by the role.

## 1. Clarify (AskUserQuestion, max 3 questions)

Ask only what changes the playbook; skip anything the request already states.
Resolve these, in priority order:

- **Image kind.** "Container" is ambiguous — always ask:
  - *application container* → image-builder type `container` (OCI archive, no kernel, no driver);
  - *bootc OS image* → `osbuild_build_bootc: true` (Rocky bootc is unverified, say so).
  - Installer ISO → `image-installer` (EL) / `minimal-installer` (Fedora). VM → `qcow2`.
- **Distro + version** as `image-builder list` names it (`rocky-10.2`,
  `almalinux-10.2`, `fedora-43`; not `rocky-10`).
- **Hardware/stack** (NVIDIA/CUDA, audio, desktop) and its package scope
  (e.g. full `cuda-toolkit` vs runtime libraries).
- **Disk layout** (ISO only): `auto` (`%pre` vg00 layout) or `interactive`
  (Anaconda Installation Destination).

Default to generate-only: the role writes files, the user runs the build.

## 2. Pick the closest existing playbook and copy its structure

| Need | Start from | Host | Blueprint source |
|------|-----------|------|------------------|
| Rocky 10 workstation ISO | `playbooks/osbuild-rocky-iso.yml` | `tinybot` | static |
| Rocky 10 NVIDIA workstation ISO | `playbooks/osbuild-rocky-iso-nvidia.yml` | `builder` | static |
| …generate-only variant (`-gen` names) | `playbooks/osbuild-rocky-iso-nvidia-generate.yml` | `builder` | static |
| …with GUI partitioning | `playbooks/osbuild-rocky-iso-nvidia-interactive.yml` | `builder` | static |
| …composed from components | `playbooks/osbuild-rocky-iso-nvidia-components.yml` | `builder` | components |
| …Intel GPU compute + oneAPI (DPC++, MKL), interactive disk | `playbooks/osbuild-rocky-iso-intel-oneapi-components.yml` | `builder` | components |
| AlmaLinux 10 workstation ISO (± NVIDIA) | `playbooks/osbuild-almalinux-iso{,-nvidia}.yml` | `tinybot` | static |
| CUDA application container | `playbooks/osbuild-rocky-cuda-container.yml` | `builder` | static |
| Host-native generic build | `playbooks/osbuild.yml` (= root `osbuild.yml`) | `osbuild_targets` | Jinja template |

### Blueprint source (exactly one applies)

1. **Components** — `osbuild_blueprint_components` non-empty. Takes
   precedence over the other two. The role merges
   `files/<target>/<major>/<arch>/components/<name>.yml` with the frame
   `files/<target>/<major>/<arch>/frames/workstation.toml` through
   `templates/blueprint-components.toml.j2`. Only `rocky/10/x86_64` has
   components today: `base anaconda gnome-desktop fonts audio multimedia
   google-chrome gui-toolkit intel-graphics intel-oneapi development
   containers-virt cockpit selection-extras nvidia`.
   Preferred for a new Rocky 10 package mix: add or drop components instead
   of copying a monolithic blueprint.
2. **Static** — `osbuild_use_blueprint_template: false` +
   `osbuild_static_blueprint_path: "files/<distro>/<major>/<arch>/<kind>/<file>.toml"`.
   Existing static blueprints: `rocky/10` and `rocky/9` workstation (± nvidia),
   `almalinux/10` workstation (± nvidia), `fedora/43` workstation
   (`-nvidia`, `-intel-oneapi`, `-igx`), `rocky/10/.../container/rocky-10-2-cuda-container.toml`.
   Use for non-installer types and for distros without components.
3. **Jinja template** — `osbuild_use_blueprint_template: true` (role default).
   Emits workstation installer modules; suits only ISO builds.

Component file schema (`tasks/components.yml` asserts `label` and a non-empty
`packages`):

```yaml
label: "Human-readable name"          # required
packages: ["pkg", "@comps-group"]     # required, non-empty; never versions
repo_urls: ["https://..."]            # appended to osbuild_extra_repo_urls
services: ["unit"]                    # merged into [customizations.services]
kernel_args: ["arg=value"]            # merged into [customizations.kernel] append
fragment: name.toml                   # optional, appended verbatim
```

- A `fragment` file may only contain array-of-tables (`[[customizations.files]]`,
  `[[customizations.repositories]]`). `[customizations.kernel]` and
  `[customizations.services]` are rendered from the merged lists; defining
  them in a fragment or the frame duplicates the table.
- The frame must not define `name`, `description`, `version`, `distro`,
  `packages`, `[customizations]`, `[customizations.kernel]` or
  `[customizations.services]`.
- `osbuild_extra_packages` is added to the merged package list.
- `osbuild_components` is a separate, older mechanism
  (`osbuild_component_defs` in `defaults/main.yml`, checked by
  `tasks/validate_components.yml`). Its `sources` feed `osbuild_sources`.
  With static or component blueprints keep it at `[base, anaconda]`
  (+ `development`, `container-tools` on same-distro hosts) — those add no
  packages.

### Hard rules (each was a real failure or verified behavior)

- `roles: - role: osbuild` — not `b08x.rhel_builder.osbuild`.
- `hosts: builder` for cross-distro playbooks (they assert Fedora or EL 10);
  `tinybot` only when the play asserts an EL 10 host. Not `localhost`: the
  role needs facts and `become`. Keep `gather_facts: false` + a `setup`
  pre_task with `become: false`, as the existing playbooks do.
- **Cross-distro target:** `osbuild_sources` and its repo dictionary
  (`vars/<host distro>.yml`) come from the *host's* `ansible_distribution`.
  For an EL target on a Fedora host (Rocky/AlmaLinux on gir), set
  `osbuild_sources: []` and supply every non-base repo through
  `osbuild_extra_repo_urls` or component `repo_urls`. Do not add the `nvidia`
  entry to `osbuild_components` for EL targets on Fedora hosts. For an EL 10
  target on an EL 10 host (Rocky or AlmaLinux target on tinybot), keep the
  default `osbuild_sources`: both EL distros share `osbuild_distro_sources_el`,
  and names missing from the host's `repo` dictionary (`rocky-*` on
  AlmaLinux) are skipped, so add those URLs to `osbuild_extra_repo_urls`.
- **Rocky depsolve repos:** Rocky playbooks pass CRB, Plus and RT as extra
  repos (`https://dl.rockylinux.org/pub/rocky/<major>/{CRB,plus,RT}/x86_64/os/`);
  the Rocky 10 `base` component carries them in `repo_urls`. On EL 10,
  `libyaml-devel` comes from CRB.
- `[[customizations.repositories]]` in a blueprint only writes `.repo` files
  into the image; depsolve ignores it. Every non-base repo a package comes from
  must be an `--extra-repo`.
- Blueprints must not contain `[[customizations.user]]`, `[[customizations.group]]`,
  `unattended` or `sudo-nopasswd` while the kickstart is injected; the role
  asserts this.
- For non-installer image types (`container`, `qcow2`, …) set
  `osbuild_kickstart_enabled: false`, `osbuild_kickstart_sudoers: false`,
  `osbuild_firstboot_enabled: false`; containers also
  `osbuild_flathub_enabled: false`.
- Blocks the role appends must not use `[[packages]]`: static blueprints and
  the component template define `packages = [...]` inline, and TOML forbids
  extending it. Files appended with `'''` literal strings must not contain `'''`.
- Variants of an existing build get their own `osbuild_blueprint_name` and
  `osbuild_output_filename`, so they do not overwrite each other's files in
  `/var/tmp/osbuild-images`. A variant may reuse the same static blueprint.
- Stamp output names with `_git_commit` (pre_task copied from existing
  playbooks) and keep the `image-builder list` assert pre_task.
- Container images: name the output `.tar` and set `osbuild_container_tag`;
  the build script then runs `podman load` + `podman tag`.
- NVIDIA in an application container: install `cuda-toolkit` (or runtime
  libs), never the `cuda` meta package — it pulls `nvidia-driver` and the
  kernel module. The host supplies the driver via nvidia-container-toolkit CDI
  (`podman run --device nvidia.com/gpu=all`).
- `ruby-build-rbenv` needs `ruby-build-ruby` next to it; without it
  `/usr/share/ruby-build` is empty and `rbenv install` fails.

## 3. Role switches worth knowing

| Variable | Default | Effect |
|----------|---------|--------|
| `osbuild_only_generate` | `true` | Write `<name>.toml` + `build-<name>.sh`; `-e osbuild_only_generate=false` builds in the play |
| `osbuild_build_bootc` | `false` | bootc mode; takes priority over `osbuild_only_generate` |
| `osbuild_blueprint_components` | `[]` | Non-empty → component-composed blueprint (§2) |
| `osbuild_components_dir` / `osbuild_blueprint_frame_path` | `<target>/<major>/<arch>/components`, `…/frames/workstation.toml` | Paths relative to `roles/osbuild/files/`, resolved from the target distro |
| `osbuild_extra_packages` | `[]` | Extra packages (template and component blueprints only) |
| `osbuild_package_pins` | `{}` | `{pkg: "ver.*"}`; template and component blueprints only, static files build with `*` |
| `osbuild_kickstart_enabled` | `true` | Embed `files/kickstart/*.ks` as `[customizations.installer.kickstart]` |
| `osbuild_kickstart_partitioning` | `auto` | `interactive` → `syncopated-interactive.ks`, no storage commands |
| `osbuild_kickstart_{root_percent,root_min_gib,reserve_percent,usr_percent,usr_max_gib,var_max_gib,home_min_gib,disk_min_gib}` | `10,16,10,80,256,128,100,40` | `auto` layout: `/`, unassigned vg00 reserve, `/usr` (capped), `/var` (rest, capped), `/home` only if ≥ home_min_gib is left. Built-in defaults in `syncopated.ks` must match `defaults/main.yml` (bats checks) |
| `osbuild_kickstart_sudoers` | `true` | `/etc/sudoers.d/90-wheel-nopasswd` |
| `osbuild_firstboot_enabled` | `true` | First-login splash (desktop images only): system setup (dnf update, reboot offer, graphical.target), then optional yadm dotfiles; `yadm bootstrap` runs in a new terminal |
| `osbuild_flathub_enabled` | `true` | `/etc/flatpak/remotes.d/flathub.flatpakrepo` (system remote `flathub`) |
| `osbuild_rocky_repo_files_enabled` | `true` | Rocky targets only: replace `rocky.repo`, `rocky-extras.repo`, `rocky-addons.repo` in the image with copies that enable `crb`, `plus`, `rt` |
| `osbuild_release_file_enabled` | `true` | `/etc/syncopated-release`: blueprint name, distro, repo commit |

Appended blocks carry `# BEGIN/END syncopated-<firstboot|flathub|rocky-repos|release|kickstart|sudoers>`
markers; grep for them in the generated `.toml`.

## 4. Add or remove packages

A package name is listed in up to three places. Which builds see a change
depends on which layer the change is made in:

| Layer | File | Read by |
|-------|------|---------|
| Taxonomy | `vars/packages/<Fedora\|Rocky\|AlmaLinux>.yml` → `system_packages.<Category>.<subcategory>` | Jinja-template blueprints, through `osbuild_component_defs` (`defaults/main.yml`) |
| Components | `roles/osbuild/files/rocky/10/x86_64/components/<name>.yml` → `packages:` | `osbuild_blueprint_components` playbooks |
| Static blueprints | `roles/osbuild/files/<distro>/<major>/<arch>/<kind>/*.toml` → `packages = [ … ]` | Playbooks with `osbuild_use_blueprint_template: false` |

Procedure:

1. **Find every list that carries the package or its neighbours.**
   `grep -rn -- '<pkg>' vars/packages roles/osbuild/files`. A change that is
   meant for "the workstation" goes into all three layers for every distro
   where the name exists, and into each variant file (`-workstation.toml`
   and `-workstation-nvidia.toml` are separate lists). Commit 3729a07
   (`ruby-build-ruby`) shows the full set of files for one addition.
2. **Confirm the name exists in the target repos before adding it.** Query
   each repo the build depsolves against (base repos plus its extra repos):

   ```bash
   dnf repoquery -q --repofrompath=r,<repo URL> --repo r \
     --qf '%{name} %{repoid}\n' <pkg>
   ```

   No output means the repo does not provide that name. EL and Fedora names
   differ; check `vars/packages/00-distributions.yml` (`package_mappings`).
   `python3 scripts/package_tracker.py verify --distro Rocky --package a,b`
   runs the same lookup against the Rocky, AlmaLinux or Fedora repo profile
   (`REPO_PROFILES`); `verify` without `--package` audits the whole taxonomy
   (exit 1 when names are missing). `add` runs it by default and skips names
   a distro's repos do not provide (`--no-verify` overrides).
   Leave the name out of a distro that has no build of it, and say so in a
   comment (the files already do this for sway on EPEL 10).
3. **Add the repo when the package needs one the build does not use yet.**
   Depsolve: the component's `repo_urls` or the playbook's
   `osbuild_extra_repo_urls`. Installed system: a
   `[[customizations.repositories]]` entry (static blueprint, component
   fragment or frame). One without the other fails depsolve or leaves the
   installed system unable to update the package.
4. **Edit the taxonomy** by hand or with the tracker:

   ```bash
   python3 scripts/package_tracker.py add    --distro All --category System --subcategory base --package a,b
   python3 scripts/package_tracker.py remove --distro Rocky --category System --subcategory base --package a
   ```

   - `--distro All` translates the name per distro through `package_mappings`
     on `add`; `remove` matches the exact name only.
   - `add` appends to the end of the subcategory list, after any comment
     block; move the line if a comment groups related names.
   - Every save rewrites the whole file: it drops the leading `---` and
     reformats `audio:\n    []` in `Rocky.yml` and `AlmaLinux.yml`. Review
     `git diff vars/packages` and revert those lines.
5. **Edit components and static blueprints by hand.**
   - Component `packages:` entries are quoted strings; comps groups start
     with `@`. Record the source repo and verification date in the file's
     comment header, as the existing components do.
   - Static blueprint entries are `{ name = "<pkg>", version = "*" },`
     inside the inline `packages = [ … ]` array; comps groups are
     `{ name = "@<group>", version = "*" }`. Never add a `[[packages]]`
     table. Keep `version = "*"`; pins belong in `osbuild_package_pins`
     (template and component blueprints only).
6. **Removing a package** also removes what exists only for it: the
   component's `services:` units, `kernel_args`, fragment files and
   `repo_urls`, and matching `[customizations.services]` /
   `[customizations.repositories]` entries in static blueprints. An explicit
   removal does not exclude the package when another package requires it;
   confirm with the manifest RPM list (§5).
7. **Verify** (§5) for every playbook whose files changed: regenerate,
   depsolve with `image-builder manifest`, and check the package is present
   (added) or absent (removed) in the manifest RPM list. Run
   `ansible-playbook roles/osbuild/tests/validate_firstboot_injection.yml`
   after editing any static blueprint (it parses every one as TOML) and
   `python3 roles/osbuild/tests/validate_schema.py` after editing
   `osbuild_component_defs`.

Commit convention: `➕ chore(packages): …` for additions, `🐛 fix(packages): …`
when the package repairs broken behavior; the body names the files and the
reason the package is needed.

## 5. Verify before reporting (all must pass)

```bash
ansible-playbook playbooks/<new>.yml                      # rc=0, "generate_only"
shellcheck /var/tmp/osbuild-images/build-<name>.sh
# Validate + depsolve without building; run in bash, not zsh (zsh does not
# word-split $args, so --extra-repo flags arrive as one argument):
bash -c 'image-builder manifest <type> --distro <distro> --arch x86_64 \
  --blueprint <name>.toml --extra-repo URL ... > m.json'  # rc=0
ansible-lint playbooks/<new>.yml roles/osbuild
```

- Inspect the manifest, not just its exit code: list RPMs from
  `sources["org.osbuild.librepo"].items[*].path` and confirm wanted packages
  are present and unwanted ones absent (e.g. no `nvidia-driver`/`kmod-nvidia`
  in a container). For ISOs, read the final kickstart from
  `sources["org.osbuild.inline"]` and run `ksvalidator -v RHEL10` on it.
- `ksvalidator` comes from pykickstart, which is not in `requirements.txt`
  and has no `.venv` in this repo by default:
  `python3 -m venv .venv && .venv/bin/pip install pykickstart`.
- When role files change, rerun the suites that cover them:

  | Changed | Command | Pass condition |
  |---------|---------|----------------|
  | kickstart, `tasks/blueprint.yml` | `ansible-playbook roles/osbuild/tests/validate_kickstart_injection.yml -e ksvalidator=.venv/bin/ksvalidator` | `failed=0`; `rescued=1` is the expected conflict case, printed as "CRITICAL FAILURE" |
  | kickstart | `bats roles/osbuild/tests/kickstart/kickstart.bats` | all ok |
  | firstboot, `tasks/blueprint.yml`, any static blueprint | `ansible-playbook roles/osbuild/tests/validate_firstboot_injection.yml` | `failed=0` |
  | `files/firstboot/` | `shellcheck -x roles/osbuild/files/firstboot/syncopated-firstboot{,-launcher}` and `bats roles/osbuild/tests/firstboot/` | clean / all ok |
  | `tasks/select_build_mode.yml` | `ansible-playbook -i roles/osbuild/tests/inventory roles/osbuild/tests/validate_build_modes.yml` | `failed=0` |
  | `osbuild_component_defs` | `python3 roles/osbuild/tests/validate_schema.py` | rc=0 |

- `/var/tmp/osbuild-images` is root-owned on gir; use a scratch dir for manual
  manifest runs.

### Expected `image-builder build --verbose` noise (not failures)

RPM scriptlets run in osbuild's sandbox, which has no block device nodes, no
syslog socket and no mounted ESP. osbuild regenerates their outputs in later
stages (`org.osbuild.fix-bls`, `org.osbuild.dracut`, `org.osbuild.grub2.*`),
and Anaconda redoes bootloader and initramfs on the target disk. Ignore:

- `Created symlink … wireplumber.service` — `systemctl preset` in wireplumber %post.
- `grub2-probe: error: failed to get canonical path of '/dev/<host root>'`
  followed by `No path or device is specified` + usage —
  `/usr/lib/kernel/install.d/20-grub.install` line 131 (kernel-core %posttrans
  → `kernel-install add`) probes `/`, which resolves to the *build host's* root
  partition. The branch is gated on `SUSE_BTRFS_SNAPSHOT_BOOTING`, unused on EL.
- `dracut[E]: No '/dev/log' or 'logger' included for syslog logging` —
  `50-dracut.install`; dracut only disables syslog logging.

A real failure is a failed osbuild stage or a non-zero `image-builder` exit.
Post-install check: `sudo grubby --info=ALL` (paths `/vmlinuz-…`, no prefix),
`lsinitrd | head`, and `cat /etc/syncopated-release` (names the source commit).

## 6. Report

Give the build command (`bash /var/tmp/osbuild-images/build-<name>.sh`), what
was verified, and what was not (no image built, no VM install test). Do not
commit unless asked.
