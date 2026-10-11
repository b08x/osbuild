# Goal: Fedora 44 Blueprint Generation

The objective is to generate an OSBuild blueprint and the corresponding build scripts for a Fedora 44 workstation installer ISO, utilizing the package selection manifest located at `build-selections/build-fedora-workstation-gx-test-20261007_133802.yaml`. We will do this by templatizing the Fedora repository configurations and creating a dedicated Ansible playbook that configures the `osbuild` role to generate the blueprint without running the final image build.

## Specifications
- Shared understanding and requirements are defined in [facts.md](facts.md).
- The execution steps are detailed in [plan.md](plan.md).

## Done Condition
This goal is done when the playbook successfully generates `workstation-gx-test.toml` and `build-workstation-gx-test.sh` in `/var/tmp/osbuild-images/`, the scripts pass `shellcheck`, and the blueprint parses properly as defined in the plan's verification steps.
