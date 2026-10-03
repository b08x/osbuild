## Purpose and Scope
This document provides a **systematic methodology** for diagnosing and resolving build failures in the OSBuild role. It focuses on:

1. **Log Architecture**: Understanding where logs are generated, stored, and how to access them.
2. **Failure Patterns**: Identifying common failure modes in `image-builder`, `bootc`, and Ansible task execution.
3. **Diagnostic Workflows**: Step-by-step procedures for isolating root causes using logs, system journals, and Ansible debug output.
4. **Tooling Integration**: Leveraging `journalctl`, `podman`, and `image-builder` CLI tools for deep inspection.

This guide assumes familiarity with the role’s [Build Modes](8-build-modes-selecting-and-configuring-for-your-use-case) and [OSBuild Composer Workflow](14-osbuild-composer-workflow-and-integration). For architectural context, refer to the [Architectural Review](27-architectural-review-design-principles-and-decisions).

---

## 1. Log Architecture and Retention

### Log Sources and Locations
The OSBuild role generates logs from **three primary sources**, each with distinct retention policies and access methods:

| **Source**               | **Location**                                      | **Retention Policy**                          | **Access Method**                          | **Content Focus**                          |
|--------------------------|--------------------------------------------------|-----------------------------------------------|--------------------------------------------|--------------------------------------------|
| **Ansible Task Logs**    | `stdout`/`stderr` (console)                      | Ephemeral (lost after playbook run)           | `-v`, `-vvv` CLI flags                     | Task execution, variable states, failures  |
| **Build Failure Reports**| `{{ osbuild_log_dir }}/build-failure-*.log`      | Persistent (if `osbuild_keep_logs: true`)     | Direct file read                           | `image-builder` stdout/stderr, timestamps  |
| **System Journal**       | `journalctl` (systemd)                           | Persistent (rotated by systemd)               | `journalctl -u osbuild-composer`           | `osbuild-composer` daemon logs             |
| **Podman Build Logs**    | `podman build --log-level=debug`                 | Ephemeral (unless redirected)                 | `podman events`, `podman logs`             | Container build steps, layer failures      |
| **Image-Builder CLI**    | `/var/log/image-builder/` (host filesystem)      | Persistent (rotated by logrotate)             | `cat /var/log/image-builder/*.log`         | CLI execution, blueprint parsing           |

**Key Variables**:
- `osbuild_log_dir`: Defaults to `{{ playbook_dir }}/logs/osbuild` (configurable in `defaults/main.yml`). Sources: [defaults/main.yml](defaults/main.yml#L42)
- `osbuild_keep_logs`: When `true`, failure reports are written to disk. Sources: [defaults/main.yml](defaults/main.yml#L45)

---

### Log Retention Configuration
To **persist logs** for post-mortem analysis:
1. **Enable Log Retention**:
   ```yaml
   osbuild_keep_logs: true
   osbuild_log_dir: "/var/log/osbuild"  # Recommended: system-wide log directory
   ```
   Sources: [defaults/main.yml](defaults/main.yml#L42-L45)

2. **Verify Directory Permissions**:
   ```bash
   sudo mkdir -p /var/log/osbuild
   sudo chown -R $(whoami):$(whoami) /var/log/osbuild
   sudo chmod 755 /var/log/osbuild
   ```

3. **Log Rotation** (Optional):
   Add a `logrotate` configuration for `osbuild`:
   ```bash
   cat > /etc/logrotate.d/osbuild <<EOF
   /var/log/osbuild/*.log {
       daily
       missingok
       rotate 7
       compress
       notifempty
       create 0640 $(whoami) $(whoami)
   }
   EOF
   ```

---

## 2. Failure Pattern Recognition

### Common Failure Modes
Build failures typically fall into **five categories**, each with distinct log signatures:

| **Failure Category**       | **Trigger**                                      | **Log Signature**                              | **Diagnostic Command**                     |
|----------------------------|--------------------------------------------------|------------------------------------------------|--------------------------------------------|
| **Blueprint Validation**   | Malformed TOML, missing fields                   | `TOML parse error` in `image-builder` stderr   | `image-builder validate blueprint.toml`    |
| **Repository Unavailable** | GPG key fetch failure, 404 errors                | `Failed to fetch repository metadata`          | `curl -v <repo_url>/repodata/repomd.xml`   |
| **Package Conflict**       | Conflicting packages in `osbuild_components`     | `Problem: package X conflicts with Y`          | `dnf repoquery --conflicts <package>`      |
| **Build Timeout**          | Large image size, slow network                   | `async task did not complete` in Ansible logs  | `journalctl -u osbuild-composer --since "1 hour ago"` |
| **Disk Space Exhaustion**  | Insufficient `/var/tmp` or `/var/lib/osbuild`    | `No space left on device` in `image-builder`   | `df -h /var/tmp /var/lib/osbuild`          |
| **Secure Boot Conflict**   | NVIDIA driver with `secure_boot_compatible: false` | `Secure Boot forbids loading module`          | `mokutil --sb-state`                       |

---

### Blueprint Validation Failures
**Symptoms**:
- `image-builder` fails with `TOML parse error` or `missing required field`.
- Ansible task `Validate TOML syntax` fails with Python `tomli` errors.

**Diagnostic Workflow**:
1. **Reproduce Locally**:
   ```bash
   python3 -c "import tomli; tomli.load(open('blueprint.toml'))"
   ```
   Sources: [tasks/blueprint.yml](tasks/blueprint.yml#L25-L35)

2. **Check for Jinja2 Template Errors**:
   - Render the template manually:
     ```bash
     ansible localhost -m template -a "src=templates/blueprint.toml.j2 dest=/tmp/blueprint.toml"
     ```
   - Validate the rendered output:
     ```bash
     image-builder validate /tmp/blueprint.toml
     ```

3. **Common Pitfalls**:
   - **Missing `name` or `version`**: Required fields in TOML blueprints. Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L1-L5)
   - **Invalid `customizations`**: Unsupported keys (e.g., `invalid_key = "value"`).
   - **Jinja2 Syntax Errors**: Unclosed `{% %}` or `{{ }}` blocks.

---

### Repository and GPG Key Failures
**Symptoms**:
- `image-builder` fails with `Failed to fetch repository metadata`.
- Ansible task `Fetch gpgkeys` fails with `404 Not Found`.

**Diagnostic Workflow**:
1. **Verify Repository Metadata**:
   ```bash
   curl -v https://<repo_url>/repodata/repomd.xml
   ```
   - Check for `HTTP 200` and valid XML.

2. **Test GPG Key Fetch**:
   ```bash
   curl -v {{ osbuild_gpgkey_url }} | gpg --with-fingerprint
   ```
   - Ensure the key is ASCII-armored and contains `BEGIN PGP PUBLIC KEY BLOCK`.

3. **Check `repo_gpgkeys` Fact**:
   ```yaml
   - name: Debug repo_gpgkeys
     ansible.builtin.debug:
       var: repo_gpgkeys
   ```
   Sources: [tasks/repo_keys.yml](tasks/repo_keys.yml#L34-L83)

4. **Common Pitfalls**:
   - **`$releasever`/`$basearch` in URLs**: These are **not interpolated** by Ansible and are passed literally to `image-builder`. Replace with hardcoded values or use `ansible.builtin.replace`. Sources: [vars/AlmaLinux.yml](vars/AlmaLinux.yml#L14-L70)
   - **Missing `gpgkey_url`**: Some repositories (e.g., `antigravity-rpm`) disable GPG checks. Set `check_gpg: false` in the repo definition. Sources: [vars/Fedora.yml](vars/Fedora.yml#L50)

---

### Package Conflict Failures
**Symptoms**:
- `image-builder` fails with `Problem: package X conflicts with Y`.
- Ansible task `Check for conflicting components` fails.

**Diagnostic Workflow**:
1. **List Conflicts for a Package**:
   ```bash
   dnf repoquery --conflicts <package_name>
   ```

2. **Check Component Conflicts**:
   - The `validate_components.yml` task checks for conflicts between selected components. Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L20-L40)
   - Example: The `desktop` alias conflicts with `sway`, but `gnome` does not. Sources: [defaults/main.yml](defaults/main.yml#L243-L262)

3. **Debug Component Dependencies**:
   ```yaml
   - name: Debug component dependencies
     ansible.builtin.debug:
       msg: "Component '{{ item }}' requires: {{ osbuild_component_defs[item].requires | default([]) }}"
     loop: "{{ osbuild_components }}"
   ```

4. **Common Pitfalls**:
   - **Implicit Conflicts**: Some packages (e.g., `gnome-shell` vs `sway`) conflict at runtime but not in metadata. Use `osbuild_component_defs` to declare explicit conflicts.
   - **Missing Dependencies**: Ensure all `requires` are satisfied. Sources: [tasks/validate_components.yml](tasks/validate_components.yml#L45-L56)

---

### Build Timeout Failures
**Symptoms**:
- Ansible task `Execute image-builder build` fails with `async task did not complete`.
- `journalctl -u osbuild-composer` shows `timeout` errors.

**Diagnostic Workflow**:
1. **Check System Resources**:
   ```bash
   free -h  # Memory
   df -h /var/tmp  # Disk space
   ```

2. **Increase Timeout**:
   ```yaml
   osbuild_build_timeout: 3600  # Default: 1800 seconds (30 minutes)
   ```
   Sources: [defaults/main.yml](defaults/main.yml#L38)

3. **Monitor `osbuild-composer`**:
   ```bash
   journalctl -u osbuild-composer -f
   ```

4. **Common Pitfalls**:
   - **Large Images**: Components like `nvidia` or `development` increase build time. Use `size_impact` and `build_time_impact` to estimate. Sources: [defaults/main.yml](defaults/main.yml#L264-L288)
   - **Network Latency**: Slow mirrors for `osbuild_extra_repo_urls`. Use `--extra-repo` with local mirrors.

---

### Secure Boot Failures
**Symptoms**:
- `image-builder` fails with `Secure Boot forbids loading module`.
- NVIDIA driver installation fails.

**Diagnostic Workflow**:
1. **Check Secure Boot State**:
   ```bash
   mokutil --sb-state
   ```

2. **Verify Component Compatibility**:
   ```yaml
   - name: Debug secure boot compatibility
     ansible.builtin.debug:
       msg: "Component '{{ item }}' secure_boot_compatible: {{ osbuild_component_defs[item].secure_boot_compatible }}"
     loop: "{{ osbuild_components }}"
   ```
   Sources: [defaults/main.yml](defaults/main.yml#L264-L288)

3. **Disable Secure Boot (Temporary)**:
   - Add `secure_boot: false` to the blueprint customizations. Sources: [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L20-L30)

4. **Common Pitfalls**:
   - **NVIDIA Driver**: The `nvidia` component sets `secure_boot_compatible: false`. Use `akmod-nvidia` or sign the driver manually. Sources: [defaults/main.yml](defaults/main.yml#L264-L288)

---

## 3. Diagnostic Workflows

### Workflow 1: Ansible Task Debugging
**Goal**: Isolate failures in Ansible task execution.

**Steps**:
1. **Run Playbook with Verbose Output**:
   ```bash
   ansible-playbook playbook.yml -e "osbuild_verbose=true" -vvv
   ```

2. **Check Task Results**:
   - Look for `FAILED` tasks and `stderr` output.
   - Example failure:
     ```
     TASK [osbuild : Execute image-builder build] ******************************
     fatal: [localhost]: FAILED! => {"changed": false, "msg": "async task did not complete"}
     ```

3. **Debug Variables**:
   ```yaml
   - name: Debug osbuild variables
     ansible.builtin.debug:
       var: hostvars[inventory_hostname]
   ```

4. **Re-run Specific Task**:
   ```bash
   ansible-playbook playbook.yml --start-at-task "Execute image-builder build"
   ```

---

### Workflow 2: `image-builder` CLI Debugging
**Goal**: Reproduce failures using the `image-builder` CLI.

**Steps**:
1. **Validate Blueprint**:
   ```bash
   image-builder validate {{ osbuild_blueprint_name }}.toml
   ```

2. **Test Build Manually**:
   ```bash
   sudo image-builder build {{ osbuild_image_type }} \
     --distro {{ osbuild_distro }} \
     --blueprint {{ osbuild_blueprint_name }}.toml \
     --extra-repo "{{ osbuild_extra_repo_urls | join('" --extra-repo "') }}" \
     --verbose
   ```

3. **Check `/var/log/image-builder/`**:
   ```bash
   sudo cat /var/log/image-builder/*.log
   ```

4. **Common Fixes**:
   - **Missing Repositories**: Add `--extra-repo` flags for third-party repos.
   - **GPG Key Errors**: Ensure `repo_gpgkeys` are fetched and valid. Sources: [tasks/repo_keys.yml](tasks/repo_keys.yml#L34-L83)

---

### Workflow 3: `bootc` Container Build Debugging
**Goal**: Debug failures in the `bootc` container build path.

**Steps**:
1. **Check Podman Build Logs**:
   ```bash
   podman build --log-level=debug -t {{ osbuild_bootc_base_image }} -f Containerfile.bootc .
   ```

2. **Inspect Intermediate Layers**:
   ```bash
   podman history {{ osbuild_bootc_base_image }}
   ```

3. **Test Container Runtime**:
   ```bash
   podman run --rm -it {{ osbuild_bootc_base_image }} /bin/bash
   ```

4. **Common Fixes**:
   - **Missing Packages**: Ensure `osbuild_components` are correctly defined in `build.sh.j2`. Sources: [templates/build.sh.j2](templates/build.sh.j2#L60-L100)
   - **Service Failures**: Check `systemctl status` for enabled services. Sources: [templates/build.sh.j2](templates/build.sh.j2#L150-L170)

---

### Workflow 4: System Journal Analysis
**Goal**: Analyze `osbuild-composer` and systemd logs.

**Steps**:
1. **Check `osbuild-composer` Logs**:
   ```bash
   journalctl -u osbuild-composer --since "1 hour ago" -f
   ```

2. **Filter for Errors**:
   ```bash
   journalctl -u osbuild-composer -p err
   ```

3. **Check Disk Space**:
   ```bash
   journalctl -u osbuild-composer | grep "No space left on device"
   ```

4. **Common Fixes**:
   - **Clean `/var/lib/osbuild`**:
     ```bash
     sudo rm -rf /var/lib/osbuild/*
     ```
   - **Restart `osbuild-composer`**:
     ```bash
     sudo systemctl restart osbuild-composer
     ```

---

## 4. Tooling Integration

### `journalctl` for System Logs
**Key Commands**:
| **Command**                                      | **Purpose**                                      |
|--------------------------------------------------|--------------------------------------------------|
| `journalctl -u osbuild-composer`                 | View all logs for `osbuild-composer`             |
| `journalctl -u osbuild-composer -f`              | Follow logs in real-time                         |
| `journalctl -u osbuild-composer --since "1h ago"`| Filter logs from the last hour                   |
| `journalctl -u osbuild-composer -p err`          | Show only error-level logs                       |
| `journalctl -u osbuild-composer -o json`         | Output logs in JSON format for parsing           |

---

### `podman` for Container Builds
**Key Commands**:
| **Command**                                      | **Purpose**                                      |
|--------------------------------------------------|--------------------------------------------------|
| `podman build --log-level=debug -t <image> .`    | Build with debug logging                         |
| `podman logs <container_id>`                     | View logs for a specific container               |
| `podman events --filter event=die`               | Monitor container failures                       |
| `podman inspect <image>`                         | Inspect image metadata                           |
| `podman history <image>`                         | View layer history                               |

---

### `image-builder` CLI
**Key Commands**:
| **Command**                                      | **Purpose**                                      |
|--------------------------------------------------|--------------------------------------------------|
| `image-builder validate blueprint.toml`          | Validate blueprint syntax                        |
| `image-builder build <type> --verbose`           | Run build with verbose output                    |
| `image-builder build <type> --dry-run`           | Test build without execution                     |
| `image-builder status`                           | Check `image-builder` service status             |

---

## 5. Proactive Debugging Strategies

### Pre-Build Validation
1. **Validate Variables**:
   ```yaml
   - name: Validate osbuild variables
     ansible.builtin.assert:
       that:
         - osbuild_blueprint_name is defined
         - osbuild_distro in ["fedora", "almalinux", "rocky"]
         - osbuild_image_type in ["iso", "qcow2", "ami", "container"]
   ```
   Sources: [tasks/main.yml](tasks/main.yml#L25-L35)

2. **Test Repository Connectivity**:
   ```yaml
   - name: Test repository connectivity
     ansible.builtin.uri:
       url: "{{ item.metalink | default(item.baseurl) }}"
       status_code: 200
     loop: "{{ osbuild_sources }}"
     when: item.metalink is defined or item.baseurl is defined
   ```

3. **Check Disk Space**:
   ```yaml
   - name: Check disk space
     ansible.builtin.assert:
       that:
         - ansible_facts.mounts | selectattr('mount', 'equalto', '/var/tmp') | map(attribute='size_available') | first > 10737418240  # 10GB
   ```

---

### Post-Failure Analysis
1. **Capture Failure Logs**:
   - The `build.yml` task writes failure reports to `{{ osbuild_log_dir }}/build-failure-*.log`. Sources: [tasks/build.yml](tasks/build.yml#L70-L90)
   - Example log entry:
     ```
     Build Failure Report
     ====================
     Timestamp: 2026-09-11T12:00:00Z
     Blueprint: workstation
     Image Type: iso
     Distribution: fedora
     Status: FAILED

     STDOUT:
     Building image...

     STDERR:
     Error: Failed to fetch repository metadata
     ```

2. **Analyze `journalctl`**:
   ```bash
   journalctl -u osbuild-composer --since "1 hour ago" | grep -i "error\|fail\|timeout"
   ```

3. **Reproduce with `image-builder` CLI**:
   ```bash
   sudo image-builder build iso --distro fedora --blueprint workstation.toml --verbose
   ```

---

## 6. Troubleshooting Guide

### Error: `TOML parse error`
**Cause**: Malformed blueprint TOML or Jinja2 template error.
**Solution**:
1. Render the template manually:
   ```bash
   ansible localhost -m template -a "src=templates/blueprint.toml.j2 dest=/tmp/blueprint.toml"
   ```
2. Validate the TOML:
   ```bash
   python3 -c "import tomli; tomli.load(open('/tmp/blueprint.toml'))"
   ```
3. Check for unclosed Jinja2 blocks or invalid TOML keys.

**Sources**: [tasks/blueprint.yml](tasks/blueprint.yml#L25-L35), [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L1-L5)

---

### Error: `Failed to fetch repository metadata`
**Cause**: Repository URL is invalid or GPG key is missing.
**Solution**:
1. Test the repository URL:
   ```bash
   curl -v https://<repo_url>/repodata/repomd.xml
   ```
2. Verify the GPG key:
   ```bash
   curl -v {{ osbuild_gpgkey_url }} | gpg --with-fingerprint
   ```
3. Check `repo_gpgkeys` fact:
   ```yaml
   - name: Debug repo_gpgkeys
     ansible.builtin.debug:
       var: repo_gpgkeys
   ```

**Sources**: [tasks/repo_keys.yml](tasks/repo_keys.yml#L34-L83), [vars/Fedora.yml](vars/Fedora.yml#L19-L78)

---

### Error: `async task did not complete`
**Cause**: Build timeout or system resource exhaustion.
**Solution**:
1. Increase timeout:
   ```yaml
   osbuild_build_timeout: 3600  # 1 hour
   ```
2. Check system resources:
   ```bash
   free -h
   df -h /var/tmp
   ```
3. Monitor `osbuild-composer`:
   ```bash
   journalctl -u osbuild-composer -f
   ```

**Sources**: [defaults/main.yml](defaults/main.yml#L38), [tasks/build.yml](tasks/build.yml#L50-L70)

---

### Error: `Secure Boot forbids loading module`
**Cause**: Incompatible component (e.g., `nvidia`) with Secure Boot enabled.
**Solution**:
1. Check Secure Boot state:
   ```bash
   mokutil --sb-state
   ```
2. Disable Secure Boot in the blueprint:
   ```toml
   [customizations]
   secure_boot = false
   ```
3. Use `akmod-nvidia` or sign the driver manually.

**Sources**: [defaults/main.yml](defaults/main.yml#L264-L288), [templates/blueprint.toml.j2](templates/blueprint.toml.j2#L20-L30)

---

### Error: `No space left on device`
**Cause**: Insufficient disk space in `/var/tmp` or `/var/lib/osbuild`.
**Solution**:
1. Check disk space:
   ```bash
   df -h /var/tmp /var/lib/osbuild
   ```
2. Clean `/var/lib/osbuild`:
   ```bash
   sudo rm -rf /var/lib/osbuild/*
   ```
3. Restart `osbuild-composer`:
   ```bash
   sudo systemctl restart osbuild-composer
   ```

**Sources**: [tasks/install.yml](tasks/install.yml#L10-L20)

---

## Next Steps
1. **For Build Optimization**: Proceed to [Performance Optimization for Large-Scale Builds](24-performance-optimization-for-large-scale-builds).
2. **For Custom Packages**: Refer to [Integrating Custom Packages and Repositories](25-integrating-custom-packages-and-repositories).
3. **For Security Hardening**: See [Security Hardening in Image Builds](26-security-hardening-in-image-builds).