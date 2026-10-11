# Changelog

All notable changes to this project will be documented in this file.
## [0.5.0] - 2026-10-11

### 🚀 Features

- 🎉 feat: initial extraction of osbuild role, playbooks, and taxonomy tracker TUI
- Feat(composer_cli): integrate composer_cli role and playbooks as alternative image builder
- ✨ feat(rocky): enable CRB, Plus and RT repositories
- ✨ feat(firstboot): fullscreen bootstrap window, complete despite skipped steps
- ✨ feat(firstboot): run ansible-pull after dnf upgrade when configured
- ✨ feat(packages): verify package availability in package_tracker
- ✨ feat(rocky): add Rocky 10.2 workstation components playbook
- ✨ feat(rocky): add Rocky 10.2 Intel oneAPI workstation components playbook
- ✨ feat: print yadm dotfiles commands instead of running them
- ✨ feat(firstboot): download yadm when missing, still print clone commands
- ✨ feat(osbuild): add b08x/syncopated COPR to default sources
- Feat: add inxi, yadm, ydotool, and gitflow packages to rocky 10 base components
- ✨ feat: fold selection-extras into components and add syncopated COPR component
- ✨ feat(osbuild): add OpenSCAP profile components and compliant disk layout
- ✨ feat(osbuild): enable cockpit, open 9090, fix kickstart tests
- ✨ feat: add Rocky 10.2 NVIDIA OpenSCAP components ISO playbook
- ✨ feat: add JupyterLab packages to EL10 development component
- ✨ feat: add ocenaudio to EL10 syncopated component
- ✨ feat: add lld linker to base components
- ✨ feat(osbuild): check extra repositories before generating and building

### 🐛 Bug Fixes

- Fix(ansible.cfg): replace deprecated community.general.yaml callback with default and callback_result_format = yaml
- 🐛 fix(packages): add ruby-build-ruby so rbenv has CRuby definitions
- 🐛 fix(firstboot): start the bootstrap terminal in its own session
- 🐛 fix(osbuild): resolve syncopated COPR packages for EL 10 builds
- 🐛 fix: disable ocenaudio in EL10 syncopated components
- 🐛 fix(osbuild): align kickstart disk layout sizes with role defaults
- 🐛 fix(osbuild): stop stranding disk space in the auto kickstart layout
- 🐛 fix(osbuild): give NVIDIA workstation builds an 80 GiB /usr

### 🚜 Refactor

- ♻️ refactor(firstboot): split system and dotfiles setup, hand off yadm bootstrap
- ♻️ refactor(osbuild): move package lists into component files
- ♻️ refactor(playbooks): use component-based blueprints
- ♻️ refactor(osbuild): move selection-extras into components
- Refactor: update default osbuild extra packages formatting and disk partition sizes
- Refactor: increase minimum disk size and adjust partition size defaults in kickstart configuration
- ♻️ refactor(osbuild): size kickstart volumes by minimum, maximum and weight

### 📚 Documentation

- Docs(wiki): update 2026-10-03-135644 documentation for standalone repo extraction and package tracker TUI
- 📝 docs(skill): update syncopated skill for the standalone repo
- 📝 docs(readme): document package list layers and tracker side effects
- 📝 docs: document Intel oneAPI playbook and current component list
- 📝 docs(readme): clarify generate-only builds and wording
- 📝 docs(readme): expand syncopated skill section with examples
- 📝 docs(osbuild): document the component-based package layout
- 📝 docs(skills): update syncopated skill for component blueprints
- 📝 docs(goals): add goal records and parity test baselines
- 📝 docs(osbuild): document OpenSCAP profiles and compliant layout
- 📝 docs: add standalone workstation hardening goal definition

### 🧪 Testing

- 📸 test(osbuild): regenerate workstation component baselines

### ⚙️ Miscellaneous Tasks

- ➕ chore(packages): add perl-IPC-Cmd and perl-FindBin to System.base
- ➕ chore(packages): add source-build dependencies to System.base
- ➕ chore(packages): add google-chrome-stable to workstation builds
- ➕ chore(packages): add python3-rich to default workstation builds
- ➕ chore(packages): add python3-psutil to default workstation builds
- ➕ chore(packages): add VS Code (code) and its repo to workstation builds
- 🔧 chore: add git, gh, glab and libxkbfile-devel to Rocky components
- 🔥 chore(osbuild): remove generated .zread wiki
- 🔧 chore(packages): add package tracker and component tests
