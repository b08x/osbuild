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
│   ├── osbuild-rocky-iso-nvidia-components.yml
│   ├── osbuild-rocky-iso-nvidia-generate.yml
│   ├── osbuild-rocky-iso-nvidia-interactive.yml
│   └── osbuild-rocky-cuda-container.yml
├── roles/                       # Standalone Ansible roles
│   ├── osbuild/                 # Primary osbuild image composer role (image-builder CLI)
│   └── composer_cli/            # Alternative composer-cli role (osbuild-composer daemon)
├── scripts/
│   └── package_tracker.py       # TUI and CLI tool for taxonomy maintenance & build tracking
├── vars/
│   └── packages/                # Canonical package taxonomy (source of truth)
│       ├── 00-distributions.yml # Cross-distribution package & repository mappings
│       ├── Fedora.yml           # Fedora package taxonomy
│       ├── AlmaLinux.yml        # AlmaLinux package taxonomy
│       └── Rocky.yml            # Rocky Linux package taxonomy
├── build-selections/            # Exported build selection manifests
├── requirements.txt             # Python dependencies
└── .agents/
    └── skills/
        └── syncopated/          # Syncopated appliance builder agent skill
```

---

## Package Tracker TUI (`scripts/package_tracker.py`)

The repository includes a modern Python-based TUI and CLI tool for managing the package taxonomy and selecting components for image builds.

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
- **Add Packages**: Interactively add packages to single or all distributions, leveraging `00-distributions.yml` mappings with `ruamel.yaml` round-trip formatting preservation.
- **Remove Packages**: Interactively select and remove packages with confirmation.

### CLI Non-Interactive Mode

The script can also be executed in scripts, automated pipelines, or CI:

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

---

## Building Images with Ansible

Run the main playbook to compose a custom workstation image:

```bash
ansible-playbook osbuild.yml
```

### Common Variants

```bash
# Rocky Linux 10.2 Workstation ISO with NVIDIA drivers
ansible-playbook playbooks/osbuild-rocky-iso-nvidia.yml

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
| `osbuild_components` | `[base, ...]` | List of component definitions to bundle into the blueprint |
| `osbuild_extra_packages` | `[]` | Additional package list injected into the build |

---

## Alternative Workflow: `composer_cli` (Daemon-Driven Builds)

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

This repository includes the **Syncopated Appliance Builder Skill** at `.agents/skills/syncopated/SKILL.md`. AI agents can reference this skill to assist with generating tailored blueprints and verifying build scripts.
