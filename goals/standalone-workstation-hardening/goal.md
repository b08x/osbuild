# Goal: Standalone Workstation Hardening

Transform the Syncopated appliance build process into an intent-driven, unattended ISO generation pipeline tailored for standalone workstations applying enterprise OpenSCAP security standards. Eliminate audit storage exhaustion and halt hazards without a mandatory centralized log collector; replace install-time disk sizing with deterministic generation-time layouts; and generate personalized, fully unattended installers driven by a single validated intent profile.

## Reference Documents
- **Shared Understanding & Fact Sheet:** [facts.md](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/goals/standalone-workstation-hardening/facts.md)
- **Execution Plan:** [plan.md](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/goals/standalone-workstation-hardening/plan.md)
- **Interview Provenance & Results:** [interview-result.json](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/goals/standalone-workstation-hardening/interview-result.json)
- **Fact Metadata:** [facts.meta.json](file:///home/b08x/WorkspaceV3/Syncopated/osbuild/goals/standalone-workstation-hardening/facts.meta.json)

## Done Condition
1. All 38 accepted outcomes in `facts.md` are implemented and verified according to `plan.md`.
2. Sizing calculations execute at generation time from `disk.size_gib`, rendering exact `logvol` directives in the kickstart, with a streamlined `%pre` disk chooser, 30-second tty countdown, and capacity / serial verification checks.
3. OpenSCAP profiles (CIS L2, PCI-DSS, HIPAA) apply workstation-tailored audit configurations (log rotation, no halt/single-user actions, warning notifications, and noise-filtered rule sets for CIS and PCI) verified through `image-builder` manifest autotailoring.
4. An optional `remote_logging` switch enables `systemd-journal-upload` over mTLS without interrupting offline or standalone workstation operations.
5. All ISO builds execute through `ansible-playbook playbooks/build.yml -e @profiles/<name>.yml` validated against `schema/intent.schema.json`.
6. Automated test suites (`pytest`, `bats`, `ansible-lint`, `shellcheck`, `ksvalidator`) pass with zero errors, and an unattended QEMU VM installation test completes successfully.
7. Physical test laptop verified running 48 hours without audit partition exhaustion or system halt.
