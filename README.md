# OSBuild Image Builder & Package Tracker

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
│   ├── osbuild-rocky-iso-components.yml
│   ├── osbuild-rocky-iso-nvidia-components.yml
│   ├── osbuild-rocky-iso-intel-oneapi-components.yml
│   ├── osbuild-rocky-iso-openscap-components.yml
│   └── osbuild-rocky-cuda-container.yml
├── roles/                       # Standalone Ansible roles
│   ├── osbuild/                 # Primary osbuild image composer role (image-builder CLI)
│   └── composer_cli/            # Alternative composer-cli role (osbuild-composer daemon)
├── scripts/
│   └── package_tracker.py       # TUI and CLI tool for the component files' package lists
├── tests/                       # pytest suite (tracker, component parity) and the render harness
├── requirements.txt             # Python dependencies
├── .agents/
│   └── skills/
│       └── syncopated/          # Syncopated appliance builder agent skill
└── .claude/
    └── skills/
        └── syncopated/          # Same SKILL.md, for Claude Code
```

---

## Package Tracker (`scripts/package_tracker.py`)

The component files are the only package data. A *target* is one `roles/osbuild/files/<distro>/<major>/<arch>/` directory: `rocky/10/x86_64`, `rocky/9/x86_64`, `almalinux/10/x86_64` or `fedora/43/x86_64`. The tracker lists, searches, adds and removes packages in `<target>/components/*.yml`. Edits touch only the `packages:` list of one file: comments, key order and the order of existing packages stay, and new packages are appended.

### CLI

```bash
# Components of a target, with label and package count
python3 scripts/package_tracker.py list --target rocky/10/x86_64

# Every target/component that contains a matching package
python3 scripts/package_tracker.py search nvidia

# Add packages (--verify checks the target's repos first; @groups skip the check)
python3 scripts/package_tracker.py add --target rocky/10/x86_64 base htop fastfetch --verify

# Remove packages (the last package of a component cannot be removed)
python3 scripts/package_tracker.py remove --target rocky/10/x86_64 base htop

# Audit a component, or a whole target, against the repos
python3 scripts/package_tracker.py verify --target rocky/10/x86_64 base
```

### Choosing a Playbook's Components

`playbook` edits the `osbuild_blueprint_components` list of a playbook without touching anything else in the file. The target comes from the playbook's `osbuild_distro`.

```bash
python3 scripts/package_tracker.py playbook playbooks/osbuild-rocky-iso-nvidia-components.yml list
python3 scripts/package_tracker.py playbook playbooks/osbuild-rocky-iso-nvidia-components.yml add gui-toolkit --after fonts
python3 scripts/package_tracker.py playbook playbooks/osbuild-rocky-iso-nvidia-components.yml remove cockpit multimedia
```

`list` shows every component of the target with `[x]` for the selected ones. `add` refuses names that have no component file for that target, and `remove` refuses to empty the list. In the TUI, choose **Components in a playbook** for a checkbox list.

`--target` is required for every command except `search`; without it the command exits with status 2 and lists the available targets. A unique prefix such as `rocky/10` works too.

If another component of the same target already has a package, `add` prints a warning naming that component and refuses the package unless you pass `--force`.

### Interactive Mode (TUI)

```bash
python3 scripts/package_tracker.py tui
```

The TUI asks for a target only when more than one exists, then lists the components (label and package count). Choosing one opens a submenu:

- **Edit packages**: a checkbox list with every package checked. Unchecked packages are removed after a confirmation that lists them.
- **Add packages**: type names (space or comma separated), optionally verify them, and confirm when another component already has a name.
- **Show details**: label, `repo_urls`, `services`, `kernel_args` and `fragment`.
- **Back**: returns to the component list, whose own **Back** returns to the target list.

### Where Package Lists Are Defined

Component files carry all package data; static blueprints (`osbuild_static_blueprint_path`) are hand-written and outside the tracker. To add a package to every workstation build, add it to the matching component in each target that provides the name (`search` shows where a name already lives). Before adding a name, confirm the target repository provides it, or use `add --verify`:

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
ansible-playbook playbooks/osbuild-rocky-iso-nvidia-components.yml

# Rocky Linux 10.2 Workstation ISO with Intel GPU compute runtime and oneAPI (DPC++, MKL),
# interactive disk layout
ansible-playbook playbooks/osbuild-rocky-iso-intel-oneapi-components.yml

# Rocky Linux 10.2 Workstation ISO hardened with one OpenSCAP profile
# (cis-l2-workstation, hipaa or pci-dss); needs a disk of at least 160 GiB
ansible-playbook playbooks/osbuild-rocky-iso-openscap-components.yml -e osbuild_openscap_profile=hipaa

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
| `osbuild_blueprint_components` | per distro in `osbuild.yml` | Component files (`files/<distro>/<major>/<arch>/components/<name>.yml`) the blueprint is composed from. The only variable that selects packages |
| `osbuild_extra_packages` | `[]` | Additional packages for component blueprints; static blueprints ignore it |

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
2. **Pick a template.** The closest playbook in `playbooks/` becomes the starting point, and the blueprint source is chosen from components or a static `.toml`.
3. **Verify.** `ansible-playbook`, `shellcheck` on the build script, an `image-builder manifest` depsolve, and `ansible-lint`. The manifest RPM list is inspected, not just its exit code.
4. **Report.** The build command, what was verified, and what was not (no image built, no VM install test).

### Examples

Each prompt below is a starting point; the skill asks about anything the prompt leaves out.

**A new image from a description**

```text
/syncopated Rocky Linux 10.2 workstation installer ISO with NVIDIA drivers, auto disk layout
```

The closest match is `playbooks/osbuild-rocky-iso-nvidia-components.yml`. The result is a playbook that writes `<name>.toml` and `build-<name>.sh` to `/var/tmp/osbuild-images`, followed by the verification run.

**A variant of an existing build**

```text
/syncopated same as the Rocky NVIDIA ISO, but with the Anaconda Installation Destination screen instead of the automatic layout
```

This maps to `osbuild_kickstart_partitioning: interactive` (see `playbooks/osbuild-rocky-iso-intel-oneapi-components.yml`). A variant gets its own `osbuild_blueprint_name` and `osbuild_output_filename`, so the original build's files stay untouched.

**A blueprint composed from components**

```text
/syncopated Rocky 10.2 ISO with Intel GPU compute runtime and oneAPI (DPC++, MKL), interactive disk layout
```

Rocky 9/10, AlmaLinux 10 and Fedora 43 builds are assembled from `roles/osbuild/files/<distro>/<major>/x86_64/components/*.yml` through `osbuild_blueprint_components`. This request lands on `playbooks/osbuild-rocky-iso-intel-oneapi-components.yml`. Adding or dropping a component changes the package mix without copying a monolithic blueprint.

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

The skill searches the component files with `scripts/package_tracker.py search` for each name, confirms the target repositories provide it, and adds it to the matching component of every target that has the name. Names that exist only on some distributions are left out of the others, with a comment saying so. The commit convention is `➕ chore(packages): …`.

**Removing a package**

```text
/syncopated drop htop from the Rocky workstation builds
```

Removal also covers what exists only for that package: component `services:` units, `kernel_args`, fragments, and `repo_urls`. An explicit removal does not exclude a package that another package requires, so the generated RPM list is checked afterwards.

**Applying edited components**

```text
/syncopated I added packages to the rocky/10 components with package_tracker.py; check the Rocky 10 NVIDIA playbook still composes what I expect
```

The skill reads the component files, compares the playbook's `osbuild_blueprint_components` with them and verifies the names (no duplicates).

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
