# OSBuild Image Builder & Package Taxonomy

Dedicated repository for composing and building custom OS appliances, immutable bootc containers, and installer ISOs across **Fedora**, **AlmaLinux**, and **Rocky Linux** using Red Hat `image-builder` and `osbuild`.

## Repository Structure

```text
├── osbuild.yml                  # Root image build playbook (image-builder CLI)
├── composer_cli.yml             # Alternative root build playbook (osbuild-composer daemon)
├── ansible.cfg                  # Ansible configuration
├── inventory/                   # Host inventories (builder nodes: gir, tinybot)
│   └── hosts.yml
├── playbooks/                   # Appliance & ISO build playbooks
│   ├── osbuild.yml
│   ├── composer_cli.yml         # Alternative daemon-driven builder playbook
│   ├── osbuild-almalinux-iso.yml
│   ├── osbuild-almalinux-iso-nvidia.yml
│   ├── osbuild-rocky-iso.yml
│   ├── osbuild-rocky-iso-nvidia.yml
│   ├── osbuild-rocky-iso-nvidia-generate.yml
│   ├── osbuild-rocky-iso-nvidia-interactive.yml
│   ├── osbuild-rocky-iso-components.yml
│   ├── osbuild-rocky-iso-nvidia-components.yml
│   ├── osbuild-rocky-iso-intel-oneapi-components.yml
│   └── osbuild-rocky-cuda-container.yml
├── roles/                       # Standalone Ansible roles
│   ├── osbuild/                 # Primary osbuild image composer role (image-builder CLI)
│   └── composer_cli/            # Alternative composer-cli role (osbuild-composer daemon)
├── scripts/
│   └── package_tracker.py       # TUI and CLI tool for taxonomy maintenance & build tracking
├── vars/
│   └── packages/                # Canonical package taxonomy (authoritative package lists)
│       ├── 00-distributions.yml # Cross-distribution package & repository mappings
│       ├── Fedora.yml           # Fedora package taxonomy
│       ├── AlmaLinux.yml        # AlmaLinux package taxonomy
│       └── Rocky.yml            # Rocky Linux package taxonomy
├── build-selections/            # Exported build selection manifests
├── requirements.txt             # Python dependencies
├── .agents/
│   └── skills/
│       └── syncopated/          # Syncopated appliance builder agent skill
└── .claude/
    └── skills/
        └── syncopated/          # Same SKILL.md, for Claude Code
```

---

## Package Tracker TUI (`scripts/package_tracker.py`)

The repository includes a Python TUI and CLI tool for managing the package taxonomy and selecting components for image builds.

### Interactive Mode (TUI)

Launch the interactive interface with `questionary` and `rich`:

```bash
python3 scripts/package_tracker.py
# or explicitly
python3 scripts/package_tracker.py tui
```

Features:
- **Select Packages & Create Build Manifest**: Interactively check off components/subcategories (base, kernel, networking, desktop, audio, nvidia) and export a build manifest (YAML, JSON, or TOML) to `build-selections/`.
- **Search Packages**: Fast lookup across Fedora, AlmaLinux, and Rocky taxonomies showing category, subcategory, and cross-distribution mappings.
- **List Taxonomy**: View categorized package lists and counts for any target distribution.
- **Add Packages**: Interactively add packages to single or all distributions, translating names per distribution through `00-distributions.yml` mappings.
- **Remove Packages**: Interactively select and remove packages with confirmation.

### CLI Non-Interactive Mode

The script can also be run from scripts or CI pipelines:

```bash
# List categories and package counts
python3 scripts/package_tracker.py list --distro Fedora

# Search for a package
python3 scripts/package_tracker.py search nvidia

# Add a package to taxonomy
python3 scripts/package_tracker.py add --distro Fedora --category Utility --subcategory tools --package "htop"

# Remove a package
python3 scripts/package_tracker.py remove --distro Fedora --category Utility --subcategory tools --package "htop"

# Generate a build manifest non-interactively
python3 scripts/package_tracker.py build \
  --distro Fedora \
  --blueprint workstation \
  --subcategories base,kernel,networking,gnome \
  --format yaml
```

Notes:
- `add` and `remove` rewrite the whole taxonomy file. Each save drops the leading `---` and reformats empty lists (`audio:\n    []` in `Rocky.yml` and `AlmaLinux.yml`). Review `git diff vars/packages` and revert those lines.
- `add` appends to the end of the subcategory list. `remove` matches the exact name only, also with `--distro All`.
- Build manifests in `build-selections/` are a record of a selection. The `osbuild` role does not read them.

### Where Package Lists Are Defined

A package name can appear in three places. Each feeds a different set of builds:

| Layer | File | Used by |
|---|---|---|
| Taxonomy | `vars/packages/<Distro>.yml` (`system_packages.<Category>.<subcategory>`) | Jinja-template blueprints (`osbuild.yml`), through `osbuild_component_defs` |
| Components | `roles/osbuild/files/rocky/10/x86_64/components/<name>.yml` (`packages:`) | The `osbuild-rocky-iso-*components.yml` playbooks |
| Static blueprints | `roles/osbuild/files/<distro>/<major>/<arch>/<kind>/*.toml` (`packages = [ … ]`) | The other `playbooks/osbuild-*.yml` playbooks |

To add a package to every workstation build, edit all three layers for each distribution that provides the name. In the static layer, edit every blueprint variant (`-workstation.toml` and `-workstation-nvidia.toml` are separate lists). Commit `3729a07` (`ruby-build-ruby`) is an example. Before adding a name, confirm the target repository provides it:

```bash
dnf repoquery -q --repofrompath=r,<repo URL> --repo r --qf '%{name} %{repoid}\n' <package>
```

The full procedure (new repositories, removals, verification) is in [SKILL.md, section 4](.claude/skills/syncopated/SKILL.md).

---

## Building Images with Ansible

Run the main playbook to generate a blueprint and a build script. Run the script to build the image:

```bash
ansible-playbook osbuild.yml
```

### Common Variants

Each command writes `<name>.toml` and `build-<name>.sh` to `/var/tmp/osbuild-images`. Run the script to build.

```bash
# Rocky Linux 10.2 Workstation ISO with NVIDIA drivers
ansible-playbook playbooks/osbuild-rocky-iso-nvidia.yml

# Rocky Linux 10.2 Workstation ISO with Intel GPU compute runtime and oneAPI (DPC++, MKL),
# interactive disk layout
ansible-playbook playbooks/osbuild-rocky-iso-intel-oneapi-components.yml

# Rocky Linux 10.2 CUDA Application Container
ansible-playbook playbooks/osbuild-rocky-cuda-container.yml

# AlmaLinux 10.2 Workstation ISO
ansible-playbook playbooks/osbuild-almalinux-iso.yml
```

### Key Role Options

| Variable | Default | Description |
|---|---|---|
| `osbuild_distro` | Auto-detected | Target OS (e.g. `fedora-43`, `rocky-10.2`, `almalinux-10.2`) |
| `osbuild_image_type` | Auto-detected | `image-installer`, `minimal-installer`, `qcow2`, `container` |
| `osbuild_only_generate` | `true` | Generates blueprint and build script without running image-builder |
| `osbuild_build_bootc` | `false` | Set `true` to build a bootc container image |
| `osbuild_components` | `[base, ...]` | Component definitions (`osbuild_component_defs`) for template blueprints; their `sources` select `--extra-repo` repositories. Not the `components/*.yml` files; see `osbuild_blueprint_components` |
| `osbuild_blueprint_components` | `[]` | Non-empty: compose the blueprint from `files/<distro>/<major>/<arch>/components/*.yml` (Rocky 10 only) |
| `osbuild_extra_packages` | `[]` | Additional packages for template and component blueprints; static blueprints ignore it |

---

## Alternative Workflow: `composer_cli` (Builds Through the osbuild-composer Daemon)

In addition to the primary `osbuild` role (which invokes Red Hat's unified `image-builder` CLI directly), the repository provides `roles/composer_cli` as an alternative daemon-driven workflow.

`composer_cli` provisions the `osbuild-composer` systemd service, configures distribution repositories (RPMFusion, CRB, EPEL), deploys declarative blueprints to `/etc/osbuild-composer/blueprints/`, and uses `composer-cli` (Fedora) or `weldr-client` (EL 9/10) over the Weldr socket API.

### Execution

```bash
# Provision osbuild-composer and push blueprint to builder hosts (gir, tinybot)
ansible-playbook composer_cli.yml

# Or execute with custom parameters and start compose immediately
ansible-playbook composer_cli.yml \
  -e composer_cli_blueprint_name="workstation" \
  -e composer_cli_compose_type="qcow2" \
  -e composer_cli_start_compose=true
```

For full options and architectural comparison, see [`roles/composer_cli/README.md`](roles/composer_cli/README.md).

---

## Agent Skill

This repository includes the **Syncopated Appliance Builder Skill** at `.agents/skills/syncopated/SKILL.md`, with an identical copy at `.claude/skills/syncopated/SKILL.md` for Claude Code. Edit both copies together.

The skill turns a plain-language request into a playbook for the `osbuild` role, writes or composes the blueprint, and verifies both. It never builds the image; the final step is running the generated `build-<name>.sh`. Invoke it from Claude Code:

```text
/syncopated <request>
```

### How a Request Is Handled

1. **Clarify.** Up to three questions, asked only when the request leaves something open: image kind (installer ISO, application container, bootc image, qcow2), distro and version as `image-builder list` names it, hardware stack, and disk layout for ISOs.
2. **Pick a template.** The closest playbook in `playbooks/` becomes the starting point, and the blueprint source is chosen from components, a static `.toml`, or the Jinja template.
3. **Verify.** `ansible-playbook`, `shellcheck` on the build script, an `image-builder manifest` depsolve, and `ansible-lint`. The manifest RPM list is inspected, not just its exit code.
4. **Report.** The build command, what was verified, and what was not (no image built, no VM install test).

### Examples

Each prompt below is a starting point; the skill asks about anything the prompt leaves out.

**A new image from a description**

```text
/syncopated Rocky Linux 10.2 workstation installer ISO with NVIDIA drivers, auto disk layout
```

The closest match is `playbooks/osbuild-rocky-iso-nvidia.yml`. The result is a playbook that writes `<name>.toml` and `build-<name>.sh` to `/var/tmp/osbuild-images`, followed by the verification run.

**A variant of an existing build**

```text
/syncopated same as the Rocky NVIDIA ISO, but with the Anaconda Installation Destination screen instead of the automatic layout
```

This maps to `osbuild_kickstart_partitioning: interactive` (see `playbooks/osbuild-rocky-iso-nvidia-interactive.yml`). A variant gets its own `osbuild_blueprint_name` and `osbuild_output_filename`, so the original build's files stay untouched.

**A blueprint composed from components**

```text
/syncopated Rocky 10.2 ISO with Intel GPU compute runtime and oneAPI (DPC++, MKL), interactive disk layout
```

Rocky 10 builds can be assembled from `roles/osbuild/files/rocky/10/x86_64/components/*.yml` through `osbuild_blueprint_components`. This request lands on `playbooks/osbuild-rocky-iso-intel-oneapi-components.yml`. Adding or dropping a component changes the package mix without copying a monolithic blueprint.

**An application container**

```text
/syncopated CUDA application container on Rocky 10.2 for running PyTorch jobs
```

"Container" is ambiguous, so the skill asks whether an OCI application image or a bootc OS image is wanted. For an application container it installs `cuda-toolkit` rather than the `cuda` meta package (which would pull in the kernel module), disables the kickstart, firstboot and Flathub injection, and tags the output so the build script can `podman load` it. The host supplies the GPU driver:

```bash
podman run --device nvidia.com/gpu=all <image>
```

**Adding a package to the workstation builds**

```text
/syncopated add perl-IPC-Cmd and perl-FindBin to the default workstation packages
```

The skill searches `vars/packages` and `roles/osbuild/files` for each name, confirms the target repositories provide it, and edits the taxonomy, the components, and every static blueprint variant. Names that exist only on some distributions are left out of the others, with a comment saying so. The commit convention is `➕ chore(packages): …`.

**Removing a package**

```text
/syncopated drop htop from the Rocky workstation builds
```

Removal also covers what exists only for that package: component `services:` units, `kernel_args`, fragments, and `repo_urls`. An explicit removal does not exclude a package that another package requires, so the manifest RPM list is checked afterwards.

**Applying a build selection**

```text
/syncopated I added packages to the taxonomy and exported build-selections/build-rocky-workstation-gx-<timestamp>.yaml; adjust the playbook to match and verify the names (no duplicates)
```

Manifests in `build-selections/` are a record; the `osbuild` role does not read them. The skill reads the selection and carries it into the playbook and the layers above.

**Keeping the skill current**

```text
update the skill instructions to reflect the latest codebase @.claude/skills/syncopated/ @.agents/skills/syncopated/
```

Both copies change together, and the README table in [Where Package Lists Are Defined](#where-package-lists-are-defined) should be checked against the result.

### Verification Commands

The skill runs these before reporting; the same commands work by hand against any generated build.

```bash
ansible-playbook playbooks/<new>.yml
shellcheck /var/tmp/osbuild-images/build-<name>.sh
ansible-lint playbooks/<new>.yml roles/osbuild

# Depsolve without building; run in bash (zsh does not word-split the repo flags)
bash -c 'image-builder manifest image-installer --distro rocky-10.2 --arch x86_64 \
  --blueprint <name>.toml --extra-repo <URL> > m.json'
```

After editing role files, the matching test suites in `roles/osbuild/tests/` apply; the table in [SKILL.md, section 5](.claude/skills/syncopated/SKILL.md) lists which suite covers which file.

> **Note:** `image-builder build` prints scriptlet errors from `grub2-probe` and `dracut` (no `/dev/log`, no block devices in the sandbox). These are expected; a failed osbuild stage or a non-zero exit code is the real signal.
