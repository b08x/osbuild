#!/usr/bin/env bats
# Tests for roles/osbuild/files/firstboot/. Fact numbers refer to
# goals/first-boot-yadm-splash/facts.md.
#
# Every test runs with a curated PATH: a per-test bin/ holding the selected
# stubs, then a symlink farm of /usr/bin without the stubbed commands. This
# lets a test remove gum or yadm even when the host has them installed.

STUBBED="git yadm curl gum sudo systemctl nm-online dnf ansible-pull xdg-terminal-exec ptyxis kgx gnome-terminal kitty foot alacritty xterm"

setup_file() {
  export SYS_BIN="$BATS_FILE_TMPDIR/sys"
  mkdir -p "$SYS_BIN"
  local f name
  for f in /usr/bin/*; do
    name=${f##*/}
    [[ " $STUBBED " == *" $name "* ]] && continue
    ln -s "$f" "$SYS_BIN/$name"
  done
}

setup() {
  ROLE_DIR="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  SCRIPT="$ROLE_DIR/files/firstboot/syncopated-firstboot"
  LAUNCHER="$ROLE_DIR/files/firstboot/syncopated-firstboot-launcher"
  DOTS=https://github.com/b08x/dots.git

  export STUB_DIR="$BATS_TEST_DIRNAME/stubs"
  export STUB_LOG="$BATS_TEST_TMPDIR/stub.log"
  export GUM_QUEUE="$BATS_TEST_TMPDIR/gum.queue"
  export CURL_QUEUE="$BATS_TEST_TMPDIR/curl.queue"
  : >"$STUB_LOG"
  : >"$GUM_QUEUE"
  : >"$CURL_QUEUE"

  export HOME="$BATS_TEST_TMPDIR/home"
  export XDG_STATE_HOME="$HOME/.local/state"
  export XDG_RUNTIME_DIR="$BATS_TEST_TMPDIR/run"
  mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
  MARKER="$XDG_STATE_HOME/syncopated/firstboot.done"

  export SYNCOPATED_OS_RELEASE="$BATS_TEST_TMPDIR/os-release"
  printf '%s\n' 'NAME="Test OS"' 'VERSION_ID="9.9"' 'ID=testos' >"$SYNCOPATED_OS_RELEASE"
  export SYNCOPATED_NO_ANIM=1
  export SYNCOPATED_CHECK_TOOLS="git gum not-a-real-tool"
  unset SYNCOPATED_DOTFILES_URL SYNCOPATED_YADM_URL
  unset WAYLAND_DISPLAY DISPLAY
  unset SUDO_RC SYSTEMCTL_DM_UNITS SYSTEMCTL_DEFAULT DNF_RC DNF_UPDATES ANSIBLE_PULL_RC SYNCOPATED_ANSIBLE_PULL_CONF

  BIN="$BATS_TEST_TMPDIR/bin"
  mkdir -p "$BIN"
  use_stubs git yadm curl gum sudo systemctl nm-online dnf
  export PATH="$BIN:$SYS_BIN"
}

use_stubs() {
  local name
  for name in "$@"; do ln -sf "$STUB_DIR/$name" "$BIN/$name"; done
}

use_terminal() {
  ln -sf "$STUB_DIR/fake-terminal" "$BIN/$1"
}

answers() {
  printf '%s\n' "$@" >"$GUM_QUEUE"
}

logged() {
  grep -qxF -- "$1" "$STUB_LOG"
}

# printed LINE : the output holds LINE, indented by two spaces, on its own.
printed() {
  grep -qxF -- "  $1" <<<"$output"
}

# --- fact 6: runtime os-release banner -------------------------------------

@test "fact 6: banner shows NAME and VERSION_ID from os-release (gum)" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"Test OS 9.9"* ]]
}

@test "fact 6: banner shows NAME and VERSION_ID from os-release (plain)" {
  rm "$BIN/gum"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"Test OS 9.9"* ]]
}

@test "fact 6: script and launcher contain no distro names" {
  run grep -niE 'rocky|alma|fedora|rhel|epel|centos|ubuntu|debian' "$SCRIPT" "$LAUNCHER"
  [ "$status" -eq 1 ]
}

# --- fact 7: splash content (non-animated parts) --------------------------

@test "fact 7: splash prints logo, double-border banner and step list" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q -- '--border double' "$STUB_LOG"
  for step in System update target; do
    [[ $output == *"$step"* ]]
  done
  [[ $output == *'"+(tt)>.'* ]]
  [[ $output != *'press enter to begin'* ]]
}

# --- fact 8: no gum --------------------------------------------------------

@test "fact 8: without gum the setup completes and prints the yadm commands" {
  rm "$BIN/gum"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  printed "yadm clone --no-bootstrap $DOTS"
  printed "yadm bootstrap"
  [ -e "$MARKER" ]
  ! grep -q '^gum ' "$STUB_LOG"
}

# --- fact 9: launcher runs as the user ------------------------------------

@test "fact 9: launcher opens a terminal running the script without sudo" {
  use_terminal ptyxis
  run "$LAUNCHER"
  [ "$status" -eq 0 ]
  grep -q '^ptyxis .*syncopated-firstboot' "$STUB_LOG"
  ! grep -q 'sudo' "$STUB_LOG"
}

@test "fact 9: launcher prefers xdg-terminal-exec over ptyxis" {
  use_terminal ptyxis
  use_terminal xdg-terminal-exec
  run "$LAUNCHER"
  [ "$status" -eq 0 ]
  grep -q '^xdg-terminal-exec ' "$STUB_LOG"
  ! grep -q '^ptyxis ' "$STUB_LOG"
}

@test "fact 9: launcher never contains sudo" {
  run grep -n 'sudo' "$LAUNCHER"
  [ "$status" -eq 1 ]
}

@test "fact 9: launcher asks the script to pause on exit instead of pausing itself" {
  use_terminal ptyxis
  run "$LAUNCHER"
  [ "$status" -eq 0 ]
  grep -q '^ptyxis .*SYNCOPATED_PAUSE_ON_EXIT=1 .*syncopated-firstboot' "$STUB_LOG"
  ! grep -q 'read ' "$STUB_LOG"
}

# --- dotfiles: commands are printed, never run ------------------------------

@test "dotfiles: yadm clone and bootstrap commands are printed in order" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"  yadm clone --no-bootstrap $DOTS"$'\n'"  yadm bootstrap"* ]]
}

@test "dotfiles: the script runs no yadm, git or curl command" {
  rm "$BIN/yadm"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -qE '^(yadm|git|curl|sudo yadm) ' "$STUB_LOG"
  [ ! -e "$HOME/.local/bin/yadm" ]
  [ ! -e "$HOME/.local/share/yadm" ]
}

@test "dotfiles: the script asks no dotfiles question" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -qE '^gum (choose|input)' "$STUB_LOG"
}

@test "fact 10: missing yadm adds the download command before the clone" {
  rm "$BIN/yadm"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  printed "mkdir -p ~/.local/bin && curl -fsSL -o ~/.local/bin/yadm https://github.com/yadm-dev/yadm/raw/master/yadm && chmod 0755 ~/.local/bin/yadm"
  [[ $output == *"~/.local/bin/yadm"*"yadm clone --no-bootstrap $DOTS"* ]]
}

@test "fact 10: an installed yadm prints no download command" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output != *"curl "* ]]
}

@test "fact 12: SYNCOPATED_DOTFILES_URL changes the printed clone URL" {
  export SYNCOPATED_DOTFILES_URL=https://example.com/me/dots.git
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  printed "yadm clone --no-bootstrap https://example.com/me/dots.git"
}

# --- fact 17: graphical.target --------------------------------------------

@test "fact 17: graphical.target is set with sudo when a display manager exists" {
  export SYSTEMCTL_DM_UNITS="gdm.service"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "sudo systemctl set-default graphical.target"
  [ "$(grep -c '^sudo systemctl ' "$STUB_LOG")" -eq 1 ]
}

@test "fact 17: no display manager means no system change" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^sudo systemctl ' "$STUB_LOG"
  ! grep -q 'set-default' "$STUB_LOG"
}

@test "fact 17: already graphical.target means no system change" {
  export SYSTEMCTL_DM_UNITS="sddm.service" SYSTEMCTL_DEFAULT="graphical.target"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^sudo systemctl ' "$STUB_LOG"
}

@test "fact 17: a sudo failure is reported and does not fail the run" {
  export SYSTEMCTL_DM_UNITS="lightdm.service" SUDO_RC=1
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"graphical.target"* ]]
  [ -e "$MARKER" ]
}

# --- fact 24: system update and reboot offer -----------------------------

@test "fact 24: dnf upgrade runs with sudo before the yadm commands are printed" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "sudo dnf -y upgrade --refresh"
  logged "dnf -y upgrade --refresh"
  [[ $output == *"System is up to date"*"yadm clone"* ]]
}

# --- ansible-pull after the system update --------------------------------

ansible_pull_conf() {
  export SYNCOPATED_ANSIBLE_PULL_CONF="$BATS_TEST_TMPDIR/ansible-pull.conf"
  printf '%s\n' "ANSIBLE_PULL_REPO=${1-https://example.com/pull.git}" "ANSIBLE_PULL_ARGS=(${2-'-i' 'localhost,' 'local.yml'})" \
    >"$SYNCOPATED_ANSIBLE_PULL_CONF"
}

@test "ansible-pull: no configuration file means no ansible_pull step" {
  use_stubs ansible-pull
  export SYNCOPATED_ANSIBLE_PULL_CONF="$BATS_TEST_TMPDIR/missing.conf"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^ansible-pull' "$STUB_LOG"
  [[ $output != *ansible_pull* ]]
}

@test "ansible-pull: runs with sudo after dnf upgrade and before the yadm commands" {
  use_stubs ansible-pull
  ansible_pull_conf
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "sudo ansible-pull -U https://example.com/pull.git -i localhost, local.yml"
  [[ $output == *"ansible_pull (ok)"*"yadm clone"* ]]
  [ "$(grep -n -m1 '^sudo dnf ' "$STUB_LOG" | cut -d: -f1)" -lt "$(grep -n -m1 '^sudo ansible-pull ' "$STUB_LOG" | cut -d: -f1)" ]
}

@test "ansible-pull: a failure is reported and setup continues" {
  use_stubs ansible-pull
  ansible_pull_conf
  export ANSIBLE_PULL_RC=3
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"ansible-pull failed (exit 3)"* ]]
  [[ $output == *"ansible_pull (failed)"* ]]
}

@test "ansible-pull: empty arguments skip the step" {
  use_stubs ansible-pull
  ansible_pull_conf https://example.com/pull.git ""
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^ansible-pull' "$STUB_LOG"
  [[ $output == *"ansible_pull (skipped)"* ]]
}

@test "ansible-pull: a missing ansible-pull command skips the step" {
  ansible_pull_conf
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"ansible-pull not found"* ]]
  [[ $output == *"ansible_pull (skipped)"* ]]
}

@test "fact 24: nothing to update means no reboot prompt" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q 'Reboot now' "$STUB_LOG"
  [ -e "$MARKER" ]
}

@test "fact 24: installed updates offer a reboot; Reboot now reboots without a marker" {
  export DNF_UPDATES=1
  answers "Reboot now"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "sudo systemctl reboot"
  [[ $output != *"yadm clone"* ]]
  [ ! -e "$MARKER" ]
}

@test "fact 24: Continue setup after updates prints the yadm commands" {
  export DNF_UPDATES=1
  answers "Continue setup"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! logged "sudo systemctl reboot"
  printed "yadm clone --no-bootstrap $DOTS"
  [ -e "$MARKER" ]
}

@test "fact 24: reboot offer works with plain prompts" {
  rm "$BIN/gum"
  export DNF_UPDATES=1
  run "$SCRIPT" <<<"1"
  [ "$status" -eq 0 ]
  logged "sudo systemctl reboot"
}

@test "fact 24: a failed update is reported and setup continues" {
  export DNF_RC=1
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"update (failed)"* ]]
  ! grep -q 'Reboot now' "$STUB_LOG"
  [ -e "$MARKER" ]
}

@test "fact 24: no dnf means the update step is skipped" {
  rm "$BIN/dnf"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q 'dnf' "$STUB_LOG"
  [[ $output == *"update (skipped)"* ]]
  [ -e "$MARKER" ]
}

# --- fact 18: no repo priorities or flatpaks ------------------------------

@test "fact 18: script does not touch DNF priorities or install flatpaks" {
  run grep -niE 'priority|flatpak install|flatpak remote|config-manager' "$SCRIPT" "$LAUNCHER"
  [ "$status" -eq 1 ]
}

# --- fact 19: tool report -------------------------------------------------

@test "fact 19: final report lists ready and missing tools without failing" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"ready"*"git"* ]]
  [[ $output == *"missing"*"not-a-real-tool"* ]]
}

@test "the yadm commands are the last thing printed before setup completes" {
  export SYSTEMCTL_DM_UNITS="gdm.service"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"Tool check"*"yadm clone"*"yadm bootstrap"*"Setup complete"* ]]
}

# --- fact 21: marker ------------------------------------------------------

@test "fact 21: printing the commands writes the per-user marker" {
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [ -e "$MARKER" ]
}

@test "fact 21: launcher does nothing when the marker exists" {
  use_terminal ptyxis
  mkdir -p "${MARKER%/*}"
  touch "$MARKER"
  run "$LAUNCHER"
  [ "$status" -eq 0 ]
  [ ! -s "$STUB_LOG" ]
}

@test "fact 21: another user's marker does not suppress the launcher" {
  use_terminal ptyxis
  mkdir -p "${MARKER%/*}"
  touch "$MARKER"
  export HOME="$BATS_TEST_TMPDIR/other" XDG_STATE_HOME=
  mkdir -p "$HOME"
  run "$LAUNCHER"
  [ "$status" -eq 0 ]
  grep -q '^ptyxis ' "$STUB_LOG"
}

# --- fact 22: retry at next login -----------------------------------------

@test "fact 22: launcher opens the splash again after a reboot" {
  use_terminal ptyxis
  export DNF_UPDATES=1
  answers "Reboot now"
  run "$SCRIPT" </dev/null
  : >"$STUB_LOG"
  run "$LAUNCHER"
  [ "$status" -eq 0 ]
  grep -q '^ptyxis ' "$STUB_LOG"
}

# --- fact 23: manual rerun ------------------------------------------------

@test "fact 23: running the script by name ignores the marker" {
  mkdir -p "${MARKER%/*}"
  touch "$MARKER"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"Test OS 9.9"* ]]
  printed "yadm bootstrap"
}

# --- concurrency ----------------------------------------------------------

@test "a second instance exits while the lock is held" {
  exec 8>"$XDG_RUNTIME_DIR/syncopated-firstboot.lock"
  flock -n 8
  run "$SCRIPT" </dev/null
  exec 8>&-
  [ "$status" -eq 0 ]
  [[ $output == *"already running"* ]]
  [[ $output != *"yadm clone"* ]]
  ! grep -q '^sudo ' "$STUB_LOG"
}
