---
name: syncopated
description: Builder agent for custom OS appliances and container images. Generates an osbuild-role playbook (plus static blueprint when needed) that writes a blueprint and build-<name>.sh, then verifies both without building.
---

# Syncopated Appliance Builder Skill

Turn a natural-language appliance request into a playbook for the `osbuild` role
(`roles/osbuild/`), verified to the point where the user only has to run the
generated build script.

## 1. Clarify (AskUserQuestion, max 3 questions)

Ask only what changes the playbook; skip anything the request already states.
Resolve these, in priority order:

- **Image kind.** "Container" is ambiguous — always ask:
  - *application container* → image-builder type `container` (OCI archive, no kernel, no driver);
  - *bootc OS image* → `osbuild_build_bootc: true` (Rocky bootc is unverified, say so).
  - Installer ISO → `image-installer` (EL) / `minimal-installer` (Fedora). VM → `qcow2`.
- **Distro + version** as `image-builder list` names it (`rocky-10.2`, not `rocky-10`).
- **Hardware/stack** (NVIDIA/CUDA, audio, desktop) and its package scope
  (e.g. full `cuda-toolkit` vs runtime libraries).
- **Disk layout** (ISO only): `auto` (`%pre` vg00 layout) or `interactive`
  (Anaconda Installation Destination).

Default to generate-only: the role writes files, the user runs the build.

## 2. Pick the closest existing playbook and copy its structure

| Need | Start from |
|------|-----------|
| EL 10 workstation ISO | `playbooks/osbuild-rocky-iso.yml` |
| EL 10 NVIDIA workstation ISO | `playbooks/osbuild-rocky-iso-nvidia.yml` |
| …with GUI partitioning | `playbooks/osbuild-rocky-iso-nvidia-interactive.yml` |
| CUDA application container | `playbooks/osbuild-rocky-cuda-container.yml` |

Hard rules (each was a real failure or verified behavior):

- `roles: - role: osbuild` — not `b08x.rhel_builder.osbuild`.
- `hosts: builder` (gir, Fedora 43, and tinybot, EL 10) for cross-distro playbooks; `tinybot` only when the play asserts an EL host. Not `localhost`:
  the role needs facts and `become`.
- **Cross-distro target:** the role takes its repo dictionary from the *host's*
  `ansible_distribution`. For an EL target on Fedora gir set
  `osbuild_sources: []` and list every non-base repo in
  `osbuild_extra_repo_urls`. Do not add the `nvidia` component for EL targets
  on Fedora hosts (its sources resolve against Fedora repos).
- `[[customizations.repositories]]` in a blueprint only writes `.repo` files
  into the image; depsolve ignores it. Every non-base repo a package comes from
  must be an `--extra-repo` (`osbuild_extra_repo_urls`).
- Prefer a **static blueprint** under
  `roles/osbuild/files/<distro>/<major>/<arch>/<kind>/` with
  `osbuild_use_blueprint_template: false`. The Jinja template emits workstation
  installer modules and suits only ISO builds.
- Blueprints must not contain `[[customizations.user]]`, `[[customizations.group]]`,
  `unattended` or `sudo-nopasswd` while the kickstart is injected; the role
  asserts this.
- For non-installer image types (`container`, `qcow2`, …) set
  `osbuild_kickstart_enabled: false`, `osbuild_kickstart_sudoers: false`,
  `osbuild_firstboot_enabled: false`; containers also
  `osbuild_flathub_enabled: false`.
- Blueprint fragments the role appends must not use `[[packages]]`: static
  blueprints define `packages = [...]` inline, and TOML forbids extending it.
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

## 3. Role switches worth knowing

| Variable | Default | Effect |
|----------|---------|--------|
| `osbuild_only_generate` | `true` | Write `<name>.toml` + `build-<name>.sh`; `-e osbuild_only_generate=false` builds in the play |
| `osbuild_build_bootc` | `false` | bootc mode; wins over `osbuild_only_generate` |
| `osbuild_kickstart_enabled` | `true` | Embed `files/kickstart/*.ks` as `[customizations.installer.kickstart]` |
| `osbuild_kickstart_partitioning` | `auto` | `interactive` → `syncopated-interactive.ks`, no storage commands |
| `osbuild_kickstart_{root_percent,root_min_gib,reserve_percent,usr_percent,usr_max_gib,var_max_gib,home_min_gib,disk_min_gib}` | `10,16,10,80,256,128,100,40` | `auto` layout: `/`, unassigned vg00 reserve, `/usr` (capped), `/var` (rest, capped), `/home` only if ≥ home_min_gib is left. Built-in defaults in `syncopated.ks` must match `defaults/main.yml` (bats checks) |
| `osbuild_kickstart_sudoers` | `true` | `/etc/sudoers.d/90-wheel-nopasswd` |
| `osbuild_firstboot_enabled` | `true` | First-login yadm splash (desktop images only) |
| `osbuild_flathub_enabled` | `true` | `/etc/flatpak/remotes.d/flathub.flatpakrepo` (system remote `flathub`) |

## 4. Verify before reporting (all must pass)

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
  `sources["org.osbuild.inline"]` and run `.venv/bin/ksvalidator -v RHEL10` on it.
- When role files change, rerun
  `ansible-playbook roles/osbuild/tests/validate_kickstart_injection.yml -e ksvalidator=.venv/bin/ksvalidator`
  (`failed=0`; `rescued=1` is the expected conflict case, which the custom
  callback prints as "CRITICAL FAILURE") and `bats roles/osbuild/tests/kickstart/kickstart.bats`.
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
Post-install check: `sudo grubby --info=ALL` (paths `/vmlinuz-…`, no prefix)
and `lsinitrd | head`.

## 5. Report

Give the build command (`bash /var/tmp/osbuild-images/build-<name>.sh`), what
was verified, and what was not (no image built, no VM install test). Do not
commit unless asked.
