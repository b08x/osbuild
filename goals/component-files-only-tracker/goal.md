# Goal: component files as the only package data, and a component-based package_tracker

Delete the legacy `osbuild_components` / `osbuild_component_defs` variables, the `vars/packages` taxonomy and template mode from the `osbuild` role, so that `osbuild_blueprint_components` plus the component files in `roles/osbuild/files/<distro>/<major>/<arch>/components/` are the only package data. Component files and frames are added for Rocky 10/9, AlmaLinux 10 and Fedora 43. Rewrite `scripts/package_tracker.py` to list, search, add and remove packages in those component files, with a TUI submenu for editing the packages of one component.

- Shared understanding: [facts.md](facts.md) (32 accepted facts; verification flags in [facts.meta.json](facts.meta.json))
- Execution plan: [plan.md](plan.md) (steps 0–10; baseline snapshot and render harness first)
- Interview record: [interview-result.json](interview-result.json), [interview-followup.json](interview-followup.json)

## Done condition

Every fact with `automatedVerification: true` holds, with this evidence:

- `grep -rnE 'osbuild_components\b|osbuild_component_defs|system_packages|vars/packages' roles playbooks osbuild.yml` prints nothing.
- `ansible-playbook --syntax-check` passes for `osbuild.yml` and every file in `playbooks/`.
- `python3 -m pytest tests/ -q` passes. This includes the tracker tests and `tests/test_component_parity.py`. The parity test checks two things: the rendered package set equals the set of each deleted static TOML, and the three `*-components.yml` blueprints are byte-identical to the baseline.

The manual facts (TUI submenu flow, 26–30; naming and schema docs, 5–6) are checked by a walkthrough of `package_tracker.py tui` against the real tree. A real image build on tinybot is the user's hand-off check; Claude does not run it.
