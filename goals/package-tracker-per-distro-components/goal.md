# Goal: per-distro component files and a component-based package_tracker

Move the `image_builder` role's component files to `roles/image_builder/vars/<distro>/<ver>/{components,frames}/` in `infra.osbuild`, make components the only package data (replacing the `vars/packages/<Distro>.yml` taxonomy and the inline `image_builder_component_defs` catalog), and rewrite `scripts/package_tracker.py` in `osbuild` to read and edit those component files per distro and version.

- Shared understanding: [facts.md](facts.md) (25 accepted facts; verification flags in [facts.meta.json](facts.meta.json))
- Execution plan: [plan.md](plan.md) (12 ordered steps, baseline snapshot first)

## Done condition

All facts with automated verification hold, evidenced by:

- the parity test showing every former catalog entry unchanged for fedora-43, almalinux-9/10 and rocky-9/10;
- green `ansible-test sanity`/`units`, ansible-lint, yamllint and `role_image_builder` integration in `infra.osbuild`;
- passing tracker tests, `pytest` and playbook syntax checks in `osbuild`.

The plan's hand-off section lists the tinybot commands for the user to run; Claude does not run them.
