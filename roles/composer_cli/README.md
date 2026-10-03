# Composer-CLI: Daemon-Driven Image Building via osbuild-composer

An Ansible role for provisioning and managing the `osbuild-composer` daemon and interacting with the Weldr API using `composer-cli` (or `weldr-client` on Enterprise Linux).

## Table of Contents

- [Overview](#overview)
- [Alternative Architecture: `composer_cli` vs `osbuild`](#alternative-architecture-composer_cli-vs-osbuild)
- [Features](#features)
- [Requirements & Distribution Support](#requirements--distribution-support)
- [Role Variables](#role-variables)
- [Usage Examples](#usage-examples)
- [License](#license)

---

## Overview

The `composer_cli` role automates the setup and lifecycle of the `osbuild-composer` service and the `composer-cli` utility across Fedora, AlmaLinux, and Rocky Linux:

1. **Distro-Specific Repositories**: Configures RPMFusion (Fedora), CRB and EPEL (AlmaLinux & Rocky Linux).
2. **Package Provisioning**: Installs `osbuild-composer` and `composer-cli` (on Fedora) or `weldr-client` (on EL 9/10).
3. **Blueprint Management**: Deploys declarative TOML blueprint definitions to `/etc/osbuild-composer/blueprints/`.
4. **Service Lifecycle**: Enables and starts the `osbuild-composer.service` systemd unit.
5. **Blueprint Registration**: Pushes blueprints into the `osbuild-composer` Weldr API and asserts successful registration.
6. **Compose Execution**: Optionally triggers asynchronous image composes (`qcow2`, `image-installer`, `tar`, etc.).

---

## Alternative Architecture: `composer_cli` vs `osbuild`

This repository provides two distinct approaches to building operating system images:

| Feature / Aspect | `roles/osbuild` (Primary) | `roles/composer_cli` (Alternative) |
|---|---|---|
| **Mechanism** | `image-builder` CLI / direct `osbuild` pipelines | `osbuild-composer` systemd daemon + Weldr API |
| **Execution Model** | Synchronous CLI or standalone bash generation | Asynchronous background daemon queues |
| **API / Protocol** | CLI arguments, local pipelines | Unix socket (`/run/weldr/api.socket`) via `composer-cli` |
| **Artifact Formats** | ISOs, bootc container disks, QCOW2, AMI | QCOW2, AMI, OpenStack, Tar, Live ISO, VHD |
| **Best Used For** | Reproducible standalone builds, CI pipelines, bootc images | Dedicated builder hosts, persistent Weldr API service |

---

## Features

- **Automated Package Resolution**: Detects distribution family and installs `composer-cli` on Fedora and `weldr-client` on AlmaLinux and Rocky Linux.
- **Repository Setup**: Automatically activates CRB and EPEL on Enterprise Linux.
- **Declarative Blueprints**: Deploys TOML blueprints and automatically pushes them to the daemon.
- **Verification Assertions**: Verifies that pushed blueprints appear in `composer-cli blueprints list`.
- **Optional Immediate Compose**: Toggle `composer_cli_start_compose: true` to kick off builds immediately.

---

## Requirements & Distribution Support

- **Supported Platforms**:
  - Fedora (40, 41, 42, 43, Rawhide)
  - AlmaLinux (8, 9, 10)
  - Rocky Linux (8, 9, 10)
  - Red Hat Enterprise Linux (8, 9, 10)
- **Privilege**: Requires root permissions (`become: true`).

---

## Role Variables

### Variables (`defaults/main.yml`)

| Variable | Default | Description |
|---|---|---|
| `composer_cli_blueprint_name` | `"workstation"` | Blueprint identifier name |
| `composer_cli_blueprint_description` | `"Composer-cli workstation blueprint..."` | Description metadata in blueprint |
| `composer_cli_blueprint_version` | `"1.0.0"` | Semantic version for blueprint |
| `composer_cli_blueprint_dir` | `"/etc/osbuild-composer/blueprints"` | Directory where blueprint TOML files are placed |
| `composer_cli_blueprint_path` | `"{{ composer_cli_blueprint_dir }}/{{ composer_cli_blueprint_name }}.toml"` | Full path to deployed blueprint file |
| `composer_cli_compose_type` | `"qcow2"` | Output compose image type (e.g. `qcow2`, `ami`, `openstack`, `tar`) |
| `composer_cli_compose_output_dir` | `"/var/lib/osbuild-composer/outputs"` | Output storage directory |
| `composer_cli_start_compose` | `false` | When `true`, triggers `composer-cli compose start` |
| `composer_cli_service_name` | `"osbuild-composer"` | Systemd service unit name |
| `composer_cli_service_state` | `"started"` | Target systemd service state |
| `composer_cli_service_enabled` | `true` | Enable `osbuild-composer` on boot |
| `composer_cli_blueprint_toml` | *(multiline string)* | Default blueprint TOML structure (customizable via vars) |

---

## Usage Examples

### Basic Setup (Push Blueprint without Starting Compose)

```yaml
- name: Setup osbuild-composer and push blueprint
  hosts: builder
  become: true
  roles:
    - role: composer_cli
```

### Start an Immediate Compose

```yaml
- name: Setup osbuild-composer and build a QCOW2 image
  hosts: builder
  become: true
  vars:
    composer_cli_blueprint_name: "rocky-workstation"
    composer_cli_compose_type: "qcow2"
    composer_cli_start_compose: true
  roles:
    - role: composer_cli
```

### Checking Compose Status Remotely

Once a compose has started, monitor progress using `composer-cli` on the builder host:

```bash
composer-cli compose status
composer-cli compose logs <UUID>
composer-cli compose image <UUID>
```

---

## License

GPL-3.0-or-later
