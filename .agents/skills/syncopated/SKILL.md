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
- Package data: the component files in
  `roles/osbuild/files/<distro>/<major>/<arch>/components/*.yml`, selected by
  `osbuild_blueprint_components` and resolved for the *target* distro
  (`osbuild_target_distribution`, derived from `osbuild_distro`). Edit them
  with `scripts/package_tracker.py` (`list|search|add|remove|verify|tui`).

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
| Rocky 10 NVIDIA workstation ISO | `playbooks/osbuild-rocky-iso-nvidia-components.yml` | `builder` | components |
| …without NVIDIA | `playbooks/osbuild-rocky-iso-components.yml` | `builder` | components |
| …hardened with an OpenSCAP profile (CIS L2, HIPAA, PCI-DSS), compliant disk layout | `playbooks/osbuild-rocky-iso-openscap-components.yml` | `builder` | components (`openscap-<profile>`) |
| …Intel GPU compute + oneAPI (DPC++, MKL), interactive disk | `playbooks/osbuild-rocky-iso-intel-oneapi-components.yml` | `builder` | components |
| AlmaLinux 10 workstation ISO (± NVIDIA) | `playbooks/osbuild-almalinux-iso{,-nvidia}.yml` | `tinybot` | components |
| CUDA application container | `playbooks/osbuild-rocky-cuda-container.yml` | `builder` | components (`cuda-container` + `frames/container.toml`) |
| Host-native generic build | `playbooks/osbuild.yml` (= root `osbuild.yml`) | `osbuild_targets` | components, chosen per `ansible_distribution` |

### Blueprint source (exactly one applies)

1. **Components** — `osbuild_blueprint_components` non-empty. The role merges
   `files/<target>/<major>/<arch>/components/<name>.yml` with the frame
   `files/<target>/<major>/<arch>/frames/workstation.toml` (set
   `osbuild_blueprint_frame_path` for another frame) through
   `templates/blueprint-components.toml.j2`. Four targets ship components:
   `rocky/10`, `rocky/9`, `almalinux/10` and `fedora/43` (all `x86_64`). They
   share `base anaconda gnome-desktop fonts audio multimedia google-chrome
   vscode intel-graphics development containers-virt cockpit nvidia`; Rocky 10
   adds `gui-toolkit intel-oneapi cuda-container`; Rocky 10 and AlmaLinux 10 add
   `syncopated` (b08x/syncopated COPR); Rocky 10 also has one `openscap-*`
   component per profile (select at most one); Fedora 43 adds `sway`. Add or drop components instead of copying a monolithic
   blueprint: `python3 scripts/package_tracker.py playbook <file> list|add|remove <component>...`
   edits a playbook's `osbuild_blueprint_components` in place. bootc builds need components too.
2. **Static** — `osbuild_blueprint_components: []` +
   `osbuild_static_blueprint_path: "<distro>/<major>/<arch>/<kind>/<file>.toml"`
   (relative to `roles/osbuild/files/`). Remaining static blueprints:
   `fedora/43` `-intel-oneapi` and `-igx`, `rocky/10` workstation (± nvidia).
   Use for non-installer types and for distros without components.

Component file schema (`tasks/components.yml` asserts `label` and a non-empty
`packages`):

```yaml
label: "Human-readable name"          # required
packages: ["pkg", "@comps-group"]     # required, non-empty; never versions
repo_urls: ["https://..."]            # appended to osbuild_extra_repo_urls
services: ["unit"]                    # merged into [customizations.services]
kernel_args: ["arg=value"]            # merged into [customizations.kernel] append
fragment: name.toml                   # optional, appended verbatim
flatpaks: ["org.app.Id"]              # optional, bootc builds only
bootc_repos: ["shell snippet"]        # optional, bootc builds only
copr_repos: ["owner/project"]         # optional, bootc builds only
```

- A `fragment` file may only contain array-of-tables (`[[customizations.files]]`,
  `[[customizations.repositories]]`). `[customizations.kernel]` and
  `[customizations.services]` are rendered from the merged lists; defining
  them in a fragment or the frame duplicates the table.
- The frame must not define `name`, `description`, `version`, `distro`,
  `packages`, `[customizations]`, `[customizations.kernel]` or
  `[customizations.services]`.
- `osbuild_extra_packages` is added to the merged package list.
- `python3 roles/osbuild/tests/validate_schema.py` checks every component file.

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
  `osbuild_extra_repo_urls` or component `repo_urls`. For an EL 10
  target on an EL 10 host (Rocky or AlmaLinux target on tinybot), keep the
  default `osbuild_sources`: both EL distros share `osbuild_distro_sources_el`,
  and names missing from the host's `repo` dictionary (`rocky-*` on
  AlmaLinux) are skipped, so add those URLs to `osbuild_extra_repo_urls`.
- **Rocky depsolve repos:** Rocky playbooks pass CRB, Plus and RT as extra
  repos (`https://dl.rockylinux.org/pub/rocky/<major>/{CRB,plus,RT}/x86_64/os/`);
  the Rocky `base` components carry them in `repo_urls`. On EL 10,
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
  `/var/tmp/osbuild-images`. A variant may reuse the same components.
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
| `osbuild_blueprint_components` | `[]` | The only package selector → component-composed blueprint (§2) |
| `osbuild_components_dir` / `osbuild_blueprint_frame_path` | `<target>/<major>/<arch>/components`, `…/frames/workstation.toml` | Paths relative to `roles/osbuild/files/`, resolved from the target distro |
| `osbuild_extra_packages` | `[]` | Extra packages (component blueprints only) |
| `osbuild_package_pins` | `{}` | `{pkg: "ver.*"}`; component blueprints only, static files build with `*` |
| `osbuild_kickstart_enabled` | `true` | Embed `files/kickstart/*.ks` as `[customizations.installer.kickstart]` |
| `osbuild_kickstart_partitioning` | `auto` | `interactive` → `syncopated-interactive.ks`, no storage commands |
| `osbuild_kickstart_{reserve_percent,reserve_max_gib,disk_min_gib}`, per volume `{root,usr,var,home}_{min_gib,max_gib,weight}` (home: no max) | `8,64,100`; `/` `20,64,1`, `/usr` `30,110,3`, `/var` `30,110,3`, `/home` `20,-,5` | `auto` layout: reserve, then every volume's minimum, then the rest shared by weight up to each maximum (Anaconda `min`/`max` + systemd-repart `Weight` model); `/home` is dropped when the minimums do not fit with it. NVIDIA workstation playbooks raise `/usr` to 80 GiB (`usr_min_gib: 80`, `disk_min_gib: 150`; compliant: `compliant_usr_gib: 80`, `compliant_disk_min_gib: 215`). Built-in defaults in `syncopated.ks` must match `defaults/main.yml` (bats checks) |
| `osbuild_kickstart_partitioning` `compliant` | `auto` | Separate `/usr`, `/var`, `/var/tmp`, `/var/log`, `/var/log/audit`, `/home` (+ `/tmp` as tmpfs or `lv`) with hardening mount options, for OpenSCAP profiles; `osbuild_kickstart_compliant_*` sizes (fixed volumes; `/var` and `/home` share the rest by weight), 180 GiB minimum, `_encrypt` for LUKS |
| `osbuild_kickstart_sudoers` | `false` | `/etc/sudoers.d/90-wheel-nopasswd` |
| `osbuild_firstboot_enabled` | `true` | First-login splash (desktop images only): system setup (dnf update, reboot offer, graphical.target), then optional yadm dotfiles; `yadm bootstrap` runs in a new terminal |
| `osbuild_flathub_enabled` | `true` | `/etc/flatpak/remotes.d/flathub.flatpakrepo` (system remote `flathub`) |
| `osbuild_rocky_repo_files_enabled` | `true` | Rocky targets only: replace `rocky.repo`, `rocky-extras.repo`, `rocky-addons.repo` in the image with copies that enable `crb`, `plus`, `rt` |
| `osbuild_release_file_enabled` | `true` | `/etc/syncopated-release`: blueprint name, distro, repo commit |

Appended blocks carry `# BEGIN/END syncopated-<firstboot|flathub|rocky-repos|release|kickstart|sudoers>`
markers; grep for them in the generated `.toml`.

## 4. Add or remove packages

The component files are the only package data: a package name lives in
`roles/osbuild/files/<distro>/<major>/<arch>/components/<name>.yml` →
`packages:`, once per target. Static blueprints (`osbuild_static_blueprint_path`)
are hand-written and outside the tracker.

Procedure:

1. **Find every component that carries the package or its neighbours.**
   `python3 scripts/package_tracker.py search <pkg>` prints every
   target/component that has it. A change meant for "the workstation" goes
   into the matching component of every target where the name exists
   (`list --target T` shows the components). Commit 3729a07
   (`ruby-build-ruby`) shows the full set of files for one addition.
2. **Confirm the name exists in the target repos before adding it.** Query
   each repo the build depsolves against (base repos plus its extra repos):

   ```bash
   dnf repoquery -q --repofrompath=r,<repo URL> --repo r \
     --qf '%{name} %{repoid}\n' <pkg>
   ```

   No output means the repo does not provide that name. EL and Fedora names
   differ. `python3 scripts/package_tracker.py add --target T COMPONENT a b --verify`
   runs the same lookup against the target's base repos plus the `repo_urls`
   of its components, and skips names no repo provides. `verify --target T
   [COMPONENT]` audits existing entries (exit 1 when names are missing).
   Leave the name out of a target that has no build of it, and say so in a
   comment (the files already do this for sway on EPEL 10).
3. **Add the repo when the package needs one the build does not use yet.**
   Depsolve: the component's `repo_urls` or the playbook's
   `osbuild_extra_repo_urls`. Installed system: a
   `[[customizations.repositories]]` entry (static blueprint, component
   fragment or frame). One without the other fails depsolve or leaves the
   installed system unable to update the package.
4. **Edit the component** with the tracker or by hand:

   ```bash
   python3 scripts/package_tracker.py add    --target rocky/10/x86_64 base a b --verify
   python3 scripts/package_tracker.py remove --target rocky/10/x86_64 base a
   python3 scripts/package_tracker.py tui    # Edit / Add / Show details per component
   ```

   - `--target` is required (exit 2 with the target list otherwise).
   - `add` appends to the end of the `packages:` list and keeps comments, key
     order and the existing order. A name already in another component of the
     same target is refused with a warning naming it, unless `--force`.
   - `remove` refuses to empty a component.
5. **By hand**, component `packages:` entries are quoted strings; comps
   groups start with `@`. Record the source repo and verification date in the
   file's comment header, as the existing components do. Static blueprint
   entries are `{ name = "<pkg>", version = "*" },` inside the inline
   `packages = [ … ]` array; never add a `[[packages]]` table. Keep
   `version = "*"`; pins belong in `osbuild_package_pins`.
6. **Removing a package** also removes what exists only for it: the
   component's `services:` units, `kernel_args`, fragment files and
   `repo_urls`, and matching `[customizations.services]` /
   `[customizations.repositories]` entries in fragments. An explicit
   removal does not exclude the package when another package requires it;
   confirm with the manifest RPM list (§5).
7. **Verify** (§5) for every playbook whose files changed: regenerate,
   depsolve with `image-builder manifest`, and check the package is present
   (added) or absent (removed) in the manifest RPM list. Run
   `ansible-playbook roles/osbuild/tests/validate_firstboot_injection.yml`
   after editing any static blueprint (it parses every one as TOML) and
   `python3 -m pytest tests -q` after editing a component file.

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
  | a component file | `python3 roles/osbuild/tests/validate_schema.py` and `python3 -m pytest tests -q` | rc=0 / all pass |

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
