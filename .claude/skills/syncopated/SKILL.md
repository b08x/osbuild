---
name: syncopated
description: Builder agent for custom OS appliances and container images. For installer ISOs it writes an intent file under profiles/ (validated against schema/intent.schema.json) and runs playbooks/build.yml; for containers and bootc images it writes an osbuild-role playbook. Generates the blueprint and build-<name>.sh, then verifies both without building.
---

# Syncopated Appliance Builder Skill

Turn a natural-language appliance request into the input of the `osbuild`
role (`roles/osbuild/`), verified to the point where the user only has to run
the generated build script.

- **Installer ISO** (any workstation): write an **intent file**
  `profiles/<name>.yml` and run `ansible-playbook playbooks/build.yml -e
  @profiles/<name>.yml`. Never write a per-variant ISO playbook; those were
  retired. Never set role variables (`osbuild_*`) in an intent.
- **Application container, bootc image, qcow2**: write or adapt a playbook
  (`playbooks/osbuild-rocky-cuda-container.yml`, `playbooks/osbuild.yml`).

Repository facts:

- Standalone repo: `ansible.cfg` sets `roles_path = ./roles` and
  `inventory = ./inventory/hosts.yml`. Group `builder` = `gir` (Fedora 43,
  local connection) and `tinybot` (AlmaLinux 10).
- `roles/composer_cli/` (`composer_cli.yml`) is the osbuild-composer/Weldr
  alternative. This skill targets `roles/osbuild/` only.
- Package data: the component files in
  `roles/osbuild/files/<distro>/<major>/<arch>/components/*.yml`, selected by
  an intent's `components` (or a playbook's `osbuild_blueprint_components`)
  and resolved for the *target* distro. Edit them with
  `scripts/package_tracker.py` (`list|search|add|remove|verify|playbook|tui`).
- `profiles/` is gitignored except `profiles/examples/`. User intents are
  local files; do not commit them unless asked, and never commit one with
  remote logging keys inline.

## 1. Clarify (AskUserQuestion, max 3 questions)

Ask only what changes the intent; skip anything the request already states.
Resolve these, in priority order:

- **Image kind.** "Container" is ambiguous — always ask:
  - *application container* → playbook, image-builder type `container` (OCI archive, no kernel, no driver);
  - *bootc OS image* → playbook, `osbuild_build_bootc: true` (Rocky bootc is unverified, say so).
  - Installer ISO → intent. VM image (`qcow2`) → playbook.
- **Distro + version** as `image-builder list` names it (`rocky-10.2`,
  `almalinux-10.2`, `fedora-43`; not `rocky-10`). Hardening needs `rocky-10.x`.
- **Hardware/stack** (NVIDIA/CUDA, Intel oneAPI, audio, desktop) → components.
- **ISO only:** hardening profile (`none`, `cis-l2-workstation`, `pci-dss`,
  `hipaa`), disk size in GiB (a "512 GB" disk is 476 GiB, "1 TB" is 931 GiB —
  declare at most the real size, or the install aborts), LUKS (`disk.encrypt`
  makes the passphrase the one installer prompt), the user name.

Default to generate-only: the role writes files, the user runs the build.

## 2. Installer ISO: write the intent

1. Copy the closest example from `profiles/examples/` to `profiles/<name>.yml`:

   | Need | Example |
   |------|---------|
   | Rocky 10.2 workstation | `rocky-10-2-workstation-components.yml` |
   | …with NVIDIA/CUDA | `rocky-10-2-workstation-nvidia-components.yml` |
   | …with Intel GPU compute + oneAPI | `rocky-10-2-workstation-intel-oneapi-components.yml` |
   | …hardened (CIS L2 / PCI-DSS / HIPAA) | `rocky-10-2-workstation-openscap-<profile>.yml` |
   | …NVIDIA + CIS | `rocky-10-2-workstation-nvidia-openscap-cis-l2-workstation.yml` |
   | AlmaLinux 10.2 (± NVIDIA) | `almalinux-10-2-workstation{,-nvidia}.yml` |

2. Edit only intent fields (`schema/intent.schema.json`, additionalProperties
   false — a typo fails validation):

   ```yaml
   intent:
     version: 1
     name: studio-gx            # outputs <name>.toml, build-<name>.sh, <name>.credentials.txt
     description: "..."         # optional
     distro: rocky-10.2
     arch: x86_64
     hostname: studio-gx
     components: [base, anaconda, gnome-desktop, ..., nvidia]   # never openscap-*
     hardening: cis-l2-workstation    # none | cis-l2-workstation | pci-dss | hipaa
     disk:
       size_gib: 931            # declared target disk size (GiB)
       encrypt: false           # true: LUKS, the installer asks the passphrase
       tmp: tmpfs               # tmpfs | lv (hardened layout)
       serial: S5GXNF0R123      # optional: abort unless the disk has this serial
     users:
       - name: ada
         gecos: "Ada Lovelace"
         groups: [audio]        # optional; wheel + component user_groups are added
         uid: 1500              # optional
         ssh_pubkey: "ssh-ed25519 AAAA... ada@laptop"   # optional
     locale: {language: en_US.UTF-8, keyboard: us, timezone: America/New_York}
     remote_logging: {enabled: false}   # or enabled: true + url, ca_cert, client_cert, client_key
     extra_packages: []         # one-off packages for this machine
     package_pins: {}           # {pkg: "1.2.*"}
   ```

3. Components: the names in `files/<target>/<major>/<arch>/components/`.
   All four targets (`rocky/10`, `rocky/9`, `almalinux/10`, `fedora/43`)
   share `base anaconda gnome-desktop fonts audio multimedia google-chrome
   vscode intel-graphics development containers-virt cockpit nvidia`; Rocky 10
   adds `gui-toolkit intel-oneapi cuda-container`; Rocky 10 and AlmaLinux 10
   add `syncopated`; Fedora 43 adds `sway`. `python3 scripts/package_tracker.py
   playbook profiles/<name>.yml list|add|remove <component>` edits the list in
   place.

### What the role derives (never put these in an intent)

The former hard rules are enforced in the role; an intent cannot set them:

- `openscap-<profile>` component, compliant disk layout, audit volume size
  (4 GiB CIS/PCI, 10 GiB HIPAA) and the workstation audit tailoring follow
  `hardening`.
- `/usr` is 80 GiB when `nvidia` or `cuda-container` is selected.
- Extra repositories come from the components' `repo_urls` only
  (`osbuild_sources` is emptied for intents; the build host's repo list never
  reaches another distro's compose). Rocky CRB, Plus and RT are in the Rocky
  `base` components.
- `[[customizations.repositories]]` only writes `.repo` files into the image;
  depsolve uses `--extra-repo` (component `repo_urls`). A package from a new
  repo needs both (component `repo_urls` + a fragment `[[customizations.repositories]]`).
- No `[[customizations.user]]`/`[[customizations.group]]`/`unattended`/
  `sudo-nopasswd` in any blueprint next to the kickstart (asserted). Users come
  from the intent through kickstart `user` lines.
- Image type: `image-installer` (EL), `minimal-installer` (Fedora).
- Output name: `<name>-<commit>.iso` (the `-dirty` suffix marks uncommitted changes).

### What the generated ISO does (to explain in the report)

- Install asks nothing (LUKS passphrase only with `disk.encrypt`). The %pre
  picks the disk (no install media/removable/read-only/USB; NVMe first, then
  largest), checks `disk.serial`, aborts if the disk is smaller than
  `disk.size_gib`, then counts down 30 s on tty8 naming model, serial and
  size — any key aborts. Volume sizes are fixed in the kickstart, computed at
  generation (`filter_plugins/disk_layout.py`); a larger disk's surplus goes to `/home`.
- Root locked; users get a throwaway password (new each generation, SHA-512 hash
  only in the ISO; plaintext in `<output>/<name>.credentials.txt`, mode 0600,
  and printed once at the end of the play) and must change it at first login.
- Hardened: auditd rotates within 512 MB (CIS/PCI) or 2 GiB (HIPAA), never
  halts/suspends/single-users; below 25% free on `/var/log/audit`,
  `syncopated-audit-warn` warns in the journal, motd, Cockpit, and a GNOME
  critical notification for wheel users at each login. CIS/PCI unselect the
  `dac_modification_*`/`file_deletion_events_*` rules. `sudo syncopated-scan`
  writes stock + tailored HTML/ARF reports to `/var/lib/syncopated/scans/<ts>/`.
- `remote_logging.enabled: true` → systemd-journal-upload over mTLS; an
  unreachable log host only produces log lines and retries.

## 3. Containers, bootc and qcow2: playbooks

| Need | Start from | Host | Blueprint source |
|------|-----------|------|------------------|
| CUDA application container | `playbooks/osbuild-rocky-cuda-container.yml` | `builder` | components (`cuda-container` + `frames/container.toml`) |
| Host-native bootc image, or a VM image (`-e osbuild_build_bootc=false -e osbuild_image_type=qcow2`; installer types are refused) | `playbooks/osbuild.yml` (= root `osbuild.yml`) | `osbuild_targets` | components, chosen per `ansible_distribution` |

- `roles: - role: osbuild`; `hosts: builder` for cross-distro playbooks (not
  `localhost`: the role needs facts and `become`). Keep `gather_facts: false`
  + a `setup` pre_task with `become: false`, the `_git_commit` pre_task and the
  `image-builder list` assert, as the container playbook does.
- For non-installer types set `osbuild_kickstart_enabled: false`,
  `osbuild_kickstart_sudoers: false`, `osbuild_firstboot_enabled: false`;
  containers also `osbuild_flathub_enabled: false`. Name container output
  `.tar` and set `osbuild_container_tag` (the build script `podman load`s it).
- NVIDIA in an application container: `cuda-toolkit` (or runtime libs), never
  the `cuda` meta package (pulls `nvidia-driver` + kmod). The host supplies the
  driver via nvidia-container-toolkit CDI (`podman run --device nvidia.com/gpu=all`).
- `ruby-build-rbenv` needs `ruby-build-ruby` next to it.

Component file schema (`tasks/components.yml` asserts `label` and a non-empty
`packages`; `python3 roles/osbuild/tests/validate_schema.py` checks every file):

```yaml
label: "Human-readable name"          # required
packages: ["pkg", "@comps-group"]     # required, non-empty; never versions
repo_urls: ["https://..."]            # --extra-repo for depsolve
services: ["unit"]                    # merged into [customizations.services]
kernel_args: ["arg=value"]            # merged into [customizations.kernel] append
user_groups: ["libvirt"]              # installer users join these groups
openscap_unselected: ["rule_id"]      # openscap-* only: tailoring unselects
fragment: name.toml                   # optional, appended verbatim (array-of-tables only)
flatpaks: ["org.app.Id"]              # optional, bootc builds only
bootc_repos: ["shell snippet"]        # optional, bootc builds only
copr_repos: ["owner/project"]         # optional, bootc builds only
```

A fragment or frame must not define `name`, `description`, `version`,
`distro`, `packages`, `[customizations]`, `[customizations.kernel]` or
`[customizations.services]` (rendered from the merged lists). Files appended
as `'''` literal strings must not contain `'''`.

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
   Depsolve: the component's `repo_urls` (intents cannot add
   repositories; a playbook may set `osbuild_extra_repo_urls`). Installed system: a
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
7. **Verify** (§5) for every example intent or playbook whose files changed: regenerate,
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
ansible-playbook playbooks/build.yml -e @profiles/<name>.yml   # rc=0, "generate_only"
shellcheck /var/tmp/osbuild-images/build-<name>.sh
# Depsolve without building; run in bash, not zsh (zsh does not word-split
# $args, so --extra-repo flags arrive as one argument):
bash -c 'image-builder manifest image-installer --distro <distro> --arch x86_64 \
  --blueprint <name>.toml --extra-repo URL ... > m.json'        # rc=0
ansible-lint
```

- The play validates the intent first; a schema error names the field
  (`intent.disk.size_gib: ...`). A too-small `disk.size_gib` fails at
  generation with the minimum the layout needs.
- Generated files are mode 0600 and owned by the connecting user;
  `/var/tmp/osbuild-images` itself is root-owned on gir. Use a scratch
  `-e osbuild_output_dir=...` for manual manifest runs. `passlib` must be
  importable by the controller Python (`dnf install python3-passlib`).
- Inspect the manifest, not just its exit code: list RPMs from
  `sources["org.osbuild.librepo"].items[*].path` and confirm wanted packages
  are present and unwanted ones absent. Hardened builds must show
  `org.osbuild.oscap.autotailor` and `org.osbuild.oscap.remediation`. For ISOs,
  read the kickstart from `sources["org.osbuild.inline"]`, replace
  `%include /tmp/partitions.ks` with the `syncopated-layout.ks` heredoc
  (`@DISK@` → `vda`) and run `ksvalidator -v RHEL10` on it
  (`pip install pykickstart`). `python3 -m pytest tests/test_manifest.py`
  does all of this for every example on a build host.
- When role files change, rerun the suites that cover them:

  | Changed | Command | Pass condition |
  |---------|---------|----------------|
  | intents, schema, any role task/template | `python3 -m pytest tests -q` | all pass (manifest/VM tests skip off the build host) |
  | `filter_plugins/disk_layout.py`, layout defaults | `python3 -m pytest tests/test_disk_sizing.py -q` | all pass |
  | kickstart `%pre` | `bats roles/osbuild/tests/kickstart/kickstart.bats` | all ok |
  | kickstart, `tasks/blueprint.yml` | `ansible-playbook roles/osbuild/tests/validate_kickstart_injection.yml -e ksvalidator=$(which ksvalidator)` | `failed=0`; `rescued=1` is the expected conflict case |
  | audit scripts (`files/scripts/`) | `bats roles/osbuild/tests/hardening` and `shellcheck -x files/scripts/*.sh` | all ok / clean |
  | OpenSCAP tailoring lists | `python3 -m pytest tests/test_openscap_tailoring.py` | all pass (needs oscap + SSG content) |
  | remote logging templates | `python3 -m pytest tests/test_journal_remote_e2e.py` | all pass (needs systemd-journal-remote) |
  | firstboot, `tasks/blueprint.yml`, any static blueprint | `ansible-playbook roles/osbuild/tests/validate_firstboot_injection.yml` | `failed=0` |
  | `files/firstboot/` | `shellcheck -x -P SCRIPTDIR roles/osbuild/files/firstboot/syncopated-firstboot{,-launcher}` and `bats roles/osbuild/tests/firstboot/` (as a non-root user) | clean / all ok |
  | `tasks/select_build_mode.yml` | `ansible-playbook -i roles/osbuild/tests/inventory roles/osbuild/tests/validate_build_modes.yml` | `failed=0` |
  | a component file | `python3 roles/osbuild/tests/validate_schema.py` and `python3 -m pytest tests -q` | rc=0 / all pass |

- Unattended install test (KVM host, after building the CIS example ISO):
  `SYNCOPATED_VM_ISO=<iso> python3 -m pytest tests/test_vm_install.py -s`
  (wraps `tests/vm/run-install-test.sh`: no-input install, layout,
  auditd.conf and a `syncopated-scan` run are checked).

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

Give the build command (`bash /var/tmp/osbuild-images/build-<name>.sh`), the
intent file path, where the temporary passwords are
(`<name>.credentials.txt`, mode 0600, and the end of the play output), what
was verified, and what was not (no image built, no VM install test). Do not
commit unless asked; never commit `profiles/<name>.yml` (gitignored).
