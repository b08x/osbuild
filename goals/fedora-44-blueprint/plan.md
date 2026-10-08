# Plan: Fedora 44 Blueprint Generation

## Solution Approach
We will adapt the existing `Fedora.yml` variable file to dynamically support Fedora 44 (and other versions) by templatizing the hardcoded repository version numbers. Then, we will create a dedicated Ansible playbook that uses the provided package selection manifest to configure and execute the `osbuild` role. This playbook will be set to generate the blueprint and build scripts without executing the final build.

## Steps

### Step 1: Templatize Repository URLs
- **Files touched**: `roles/osbuild/vars/Fedora.yml`
- **Action**: Replace hardcoded `43` in URLs with Jinja templating `{{ osbuild_distro.split('-')[1] }}`. Ensure the syntax works correctly when Ansible interpolates variables during the role execution.
- **Verification**: `grep -q "{{ osbuild_distro.split('-')\[1\] }}" roles/osbuild/vars/Fedora.yml` to confirm the template is in place.

### Step 2: Create Dedicated Playbook
- **Files touched**: `playbooks/osbuild-fedora-workstation-gx-test.yml`
- **Action**: Create the playbook. It should:
  - Target `osbuild_targets` or `builder` (typically `gather_facts: true`).
  - Include variables directly from `build-selections/build-fedora-workstation-gx-test-20261007_133802.yaml`.
  - Override specific variables: `osbuild_distro: fedora-44`, `osbuild_kickstart_partitioning: interactive`, `osbuild_only_generate: true`, and ensure the blueprint name is correct.
- **Verification**: `ansible-playbook --syntax-check playbooks/osbuild-fedora-workstation-gx-test.yml` completes successfully.

### Step 3: Run Playbook to Generate Artifacts
- **Action**: Execute the new playbook locally to generate the `.toml` blueprint and `.sh` build script.
- **Verification**: Ensure the output files exist in `/var/tmp/osbuild-images/`.

### Step 4: Validate Generated Blueprint
- **Action**: Run `shellcheck` on the generated shell script. Optionally run an `image-builder manifest` check to ensure dependency resolution succeeds for the generated blueprint.
- **Verification**: 
  - `shellcheck /var/tmp/osbuild-images/build-workstation-gx-test.sh` exits with 0.
  - The blueprint parses correctly.

## Risks & Open Questions
- There is a minor risk that some packages in the selection manifest are not available on Fedora 44 repositories (since the manifest was generated for Fedora 43). Any missing packages will be caught during the `image-builder manifest` verification step.
