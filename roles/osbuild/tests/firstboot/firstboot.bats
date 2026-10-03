#!/usr/bin/env bats
# Tests for roles/osbuild/files/firstboot/. Fact numbers refer to
# goals/first-boot-yadm-splash/facts.md.
#
# Every test runs with a curated PATH: a per-test bin/ holding the selected
# stubs, then a symlink farm of /usr/bin without the stubbed commands. This
# lets a test remove gum or yadm even when the host has them installed.

STUBBED="git yadm curl gum sudo systemctl nm-online dnf xdg-terminal-exec ptyxis kgx gnome-terminal kitty foot alacritty xterm"

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
  unset SYNCOPATED_DOTFILES_URL SYNCOPATED_YADM_URL SYNCOPATED_WINDOW_TIMEOUT
  # No graphical session unless a test sets one: yadm bootstrap then runs in
  # the same terminal, as the tests without a terminal stub expect.
  unset WAYLAND_DISPLAY DISPLAY
  unset YADM_CLONE_RC YADM_BOOTSTRAP_RC SUDO_RC SYSTEMCTL_DM_UNITS SYSTEMCTL_DEFAULT DNF_RC DNF_UPDATES

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

# use_live_terminal NAME : a terminal stub that runs its bash -c command.
use_live_terminal() {
  ln -sf "$STUB_DIR/live-terminal" "$BIN/$1"
}

answers() {
  printf '%s\n' "$@" >"$GUM_QUEUE"
}

logged() {
  grep -qxF -- "$1" "$STUB_LOG"
}

# --- fact 6: runtime os-release banner -------------------------------------

@test "fact 6: banner shows NAME and VERSION_ID from os-release (gum)" {
  answers "Skip for now"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"Test OS 9.9"* ]]
}

@test "fact 6: banner shows NAME and VERSION_ID from os-release (plain)" {
  rm "$BIN/gum"
  run "$SCRIPT" <<<"2"
  [ "$status" -eq 0 ]
  [[ $output == *"Test OS 9.9"* ]]
}

@test "fact 6: script and launcher contain no distro names" {
  run grep -niE 'rocky|alma|fedora|rhel|epel|centos|ubuntu|debian' "$SCRIPT" "$LAUNCHER"
  [ "$status" -eq 1 ]
}

# --- fact 7: splash content (non-animated parts) --------------------------

@test "fact 7: splash prints logo, double-border banner and step list" {
  answers "Skip for now"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q -- '--border double' "$STUB_LOG"
  for step in update yadm clone bootstrap system done; do
    [[ $output == *"$step"* ]]
  done
  [[ $output == *'"+(tt)>.'* ]]
  [[ $output != *'press enter to begin'* ]]
}

# --- fact 8: no gum --------------------------------------------------------

@test "fact 8: without gum the full setup completes with plain prompts" {
  rm "$BIN/gum"
  run "$SCRIPT" < <(printf '1\n\n')
  [ "$status" -eq 0 ]
  logged "yadm clone --no-bootstrap $DOTS"
  logged "yadm bootstrap"
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

# --- fact 10: yadm download ------------------------------------------------

@test "fact 10: missing yadm is downloaded to ~/.local/bin/yadm and made executable" {
  rm "$BIN/yadm"
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q '^curl .*https://github.com/yadm-dev/yadm/raw/master/yadm' "$STUB_LOG"
  [ -x "$HOME/.local/bin/yadm" ]
  logged "yadm clone --no-bootstrap $DOTS"
}

@test "fact 10: an installed yadm is used without downloading" {
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^curl ' "$STUB_LOG"
  [ ! -e "$HOME/.local/bin/yadm" ]
}

# --- fact 11: GitHub unreachable ------------------------------------------

@test "fact 11: download failure offers Retry, and a retry succeeds" {
  rm "$BIN/yadm"
  printf '6\n0\n' >"$CURL_QUEUE"
  answers "Set up dotfiles" "Retry" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"unreachable"* ]]
  grep -q '^gum choose .*Retry.*Skip' "$STUB_LOG"
  [ "$(grep -c '^curl ' "$STUB_LOG")" -eq 2 ]
  [ -x "$HOME/.local/bin/yadm" ]
}

@test "fact 11: download failure then Skip exits cleanly without a marker" {
  rm "$BIN/yadm"
  printf '6\n' >"$CURL_QUEUE"
  answers "Set up dotfiles" "Skip"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"unreachable"* ]]
  [[ $output != *"line "*": "* ]]
  ! grep -q '^yadm clone' "$STUB_LOG"
  [ ! -e "$MARKER" ]
}

# --- fact 12: pre-filled URL ----------------------------------------------

@test "fact 12: URL prompt is pre-filled with b08x/dots" {
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -qF -- "gum input" "$STUB_LOG"
  grep -qF -- "--value $DOTS" "$STUB_LOG"
}

@test "fact 12: an edited URL is the one cloned" {
  answers "Set up dotfiles" "https://example.com/me/dots.git"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "yadm clone --no-bootstrap https://example.com/me/dots.git"
}

# --- fact 13: ls-remote validation ----------------------------------------

@test "fact 13: an unreachable URL shows an error and re-prompts" {
  answers "Set up dotfiles" "https://example.com/bad.git" "$DOTS"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q '^git ls-remote .*https://example.com/bad.git' "$STUB_LOG"
  [[ $output == *"Cannot read repository https://example.com/bad.git"* ]]
  [ "$(grep -c '^gum input' "$STUB_LOG")" -eq 2 ]
  ! grep -q '^yadm clone .*bad' "$STUB_LOG"
  logged "yadm clone --no-bootstrap $DOTS"
}

@test "fact 13: cancelling the prompt skips without a marker" {
  answers "Set up dotfiles"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^yadm clone' "$STUB_LOG"
  [ ! -e "$MARKER" ]
}

# --- fact 14: user-level yadm ---------------------------------------------

@test "fact 14: yadm clone and bootstrap run directly, not through sudo" {
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "yadm clone --no-bootstrap $DOTS"
  logged "yadm bootstrap"
  ! grep -q '^sudo .*yadm' "$STUB_LOG"
  [ -d "$HOME/.local/share/yadm/repo.git" ]
}

# --- fact 16: existing repo -----------------------------------------------

@test "fact 16: an existing yadm repo is not cloned again; bootstrap only" {
  mkdir -p "$HOME/.local/share/yadm/repo.git"
  answers "Set up dotfiles" "Run bootstrap only"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^yadm clone' "$STUB_LOG"
  ! grep -q '^gum input' "$STUB_LOG"
  logged "yadm bootstrap"
  [ -e "$MARKER" ]
}

@test "fact 16: an existing yadm repo can be skipped" {
  mkdir -p "$HOME/.local/share/yadm/repo.git"
  answers "Set up dotfiles" "Skip"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^yadm bootstrap' "$STUB_LOG"
  [ ! -e "$MARKER" ]
}

# --- fact 17: graphical.target --------------------------------------------

@test "fact 17: graphical.target is set with sudo when a display manager exists" {
  export SYSTEMCTL_DM_UNITS="gdm.service"
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "sudo systemctl set-default graphical.target"
  [ "$(grep -c '^sudo systemctl ' "$STUB_LOG")" -eq 1 ]
}

@test "fact 17: no display manager means no system change" {
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^sudo systemctl ' "$STUB_LOG"
  ! grep -q 'set-default' "$STUB_LOG"
}

@test "fact 17: already graphical.target means no system change" {
  export SYSTEMCTL_DM_UNITS="sddm.service" SYSTEMCTL_DEFAULT="graphical.target"
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^sudo systemctl ' "$STUB_LOG"
}

@test "fact 17: a sudo failure is reported and does not fail the run" {
  export SYSTEMCTL_DM_UNITS="lightdm.service" SUDO_RC=1
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"graphical.target"* ]]
  [ -e "$MARKER" ]
}

# --- fact 24: system update and reboot offer -----------------------------

@test "fact 24: dnf upgrade runs with sudo before the dotfiles prompt" {
  answers "Skip for now"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  logged "sudo dnf -y upgrade --refresh"
  logged "dnf -y upgrade --refresh"
  [ "$(grep -n -m1 '^sudo dnf ' "$STUB_LOG" | cut -d: -f1)" -lt "$(grep -n -m1 '^gum choose' "$STUB_LOG" | cut -d: -f1)" ]
}

@test "fact 24: nothing to update means no reboot prompt" {
  answers "Set up dotfiles" "__default__"
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
  ! grep -q '^yadm clone' "$STUB_LOG"
  [ ! -e "$MARKER" ]
}

@test "fact 24: Continue setup after updates runs the dotfiles setup" {
  export DNF_UPDATES=1
  answers "Continue setup" "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! logged "sudo systemctl reboot"
  logged "yadm clone --no-bootstrap $DOTS"
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
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"update (failed)"* ]]
  ! grep -q 'Reboot now' "$STUB_LOG"
  [ -e "$MARKER" ]
}

@test "fact 24: no dnf means the update step is skipped" {
  rm "$BIN/dnf"
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q 'dnf' "$STUB_LOG"
  [[ $output == *"update (skipped)"* ]]
  [ -e "$MARKER" ]
}

# --- fact 15: yadm bootstrap in a separate window --------------------------

@test "fact 15: yadm bootstrap runs in a new terminal window and setup waits for it" {
  export WAYLAND_DISPLAY=wayland-test
  use_live_terminal kitty
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q '^kitty bash -c .*syncopated-firstboot --bootstrap-window ' "$STUB_LOG"
  [ "$(grep -c '^yadm bootstrap$' "$STUB_LOG")" -eq 1 ]
  [[ $output == *"running in a new window"* ]]
  [[ $output == *"bootstrap (ok)"* ]]
  [ -e "$MARKER" ]
  [ -z "$(find "$XDG_RUNTIME_DIR" -name 'syncopated-bootstrap.*')" ]
}

@test "fact 15: ptyxis opens the bootstrap window with --new-window" {
  export WAYLAND_DISPLAY=wayland-test
  use_live_terminal ptyxis
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q '^ptyxis --new-window -- bash -c ' "$STUB_LOG"
  [ -e "$MARKER" ]
}

@test "fact 15: a failed bootstrap in the window fails setup without a marker" {
  export WAYLAND_DISPLAY=wayland-test YADM_BOOTSTRAP_RC=3
  use_live_terminal kitty
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 1 ]
  [[ $output == *"status 3"* ]]
  [ ! -e "$MARKER" ]
}

@test "fact 15: without a graphical session bootstrap runs in the same terminal" {
  use_live_terminal kitty
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  ! grep -q '^kitty ' "$STUB_LOG"
  logged "yadm bootstrap"
  [[ $output == *"Running yadm bootstrap here"* ]]
  [ -e "$MARKER" ]
}

@test "fact 15: a window that never starts falls back to the same terminal" {
  export WAYLAND_DISPLAY=wayland-test SYNCOPATED_WINDOW_TIMEOUT=1
  use_terminal kitty
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q '^kitty ' "$STUB_LOG"
  [ "$(grep -c '^yadm bootstrap$' "$STUB_LOG")" -eq 1 ]
  [ -e "$MARKER" ]
}

@test "fact 15: a late window does not run bootstrap after the timeout" {
  status_file="$BATS_TEST_TMPDIR/status"
  printf 'cancelled\n' >"$status_file"
  run "$SCRIPT" --bootstrap-window "$status_file" "$BIN/yadm" </dev/null
  [ "$status" -eq 1 ]
  ! grep -q '^yadm bootstrap' "$STUB_LOG"
}

@test "fact 15: a window closed during bootstrap records status 129" {
  status_file="$BATS_TEST_TMPDIR/status"
  : >"$status_file"
  # $BIN/yadm is a symlink into stubs/; replace the link, never write through it.
  rm "$BIN/yadm"
  printf '%s\n' '#!/usr/bin/env bash' 'kill -HUP "$PPID"; sleep 5' >"$BIN/yadm"
  chmod +x "$BIN/yadm"
  run "$SCRIPT" --bootstrap-window "$status_file" "$BIN/yadm" </dev/null
  [ "$(<"$status_file")" = 129 ]
}

# --- fact 18: no repo priorities or flatpaks ------------------------------

@test "fact 18: script does not touch DNF priorities or install flatpaks" {
  run grep -niE 'priority|flatpak install|flatpak remote|config-manager' "$SCRIPT" "$LAUNCHER"
  [ "$status" -eq 1 ]
}

# --- fact 19: tool report -------------------------------------------------

@test "fact 19: final report lists ready and missing tools without failing" {
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"ready"*"git"* ]]
  [[ $output == *"missing"*"not-a-real-tool"* ]]
}

# --- fact 20: three choices -----------------------------------------------

@test "fact 20: splash offers Set up dotfiles, Skip for now, Never ask again" {
  answers "Skip for now"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  grep -q '^gum choose .*Set up dotfiles Skip for now Never ask again$' "$STUB_LOG"
}

# --- fact 21: marker ------------------------------------------------------

@test "fact 21: successful bootstrap writes the per-user marker" {
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [ -e "$MARKER" ]
}

@test "fact 21: Never ask again writes the marker without cloning" {
  answers "Never ask again"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [ -e "$MARKER" ]
  ! grep -q '^yadm ' "$STUB_LOG"
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

@test "fact 22: Skip for now writes no marker" {
  answers "Skip for now"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [ ! -e "$MARKER" ]
}

@test "fact 22: a failed clone writes no marker and exits non-zero" {
  export YADM_CLONE_RC=1
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -ne 0 ]
  [ ! -e "$MARKER" ]
  ! grep -q '^yadm bootstrap' "$STUB_LOG"
}

@test "fact 22: a failed bootstrap writes no marker and exits non-zero" {
  export YADM_BOOTSTRAP_RC=1
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -ne 0 ]
  [ ! -e "$MARKER" ]
}

@test "fact 22: launcher opens the splash again after a skip" {
  use_terminal ptyxis
  answers "Skip for now"
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
  answers "Set up dotfiles" "__default__"
  run "$SCRIPT" </dev/null
  [ "$status" -eq 0 ]
  [[ $output == *"Test OS 9.9"* ]]
  logged "yadm bootstrap"
}

# --- concurrency ----------------------------------------------------------

@test "a second instance exits while the lock is held" {
  answers "Set up dotfiles" "__default__"
  exec 8>"$XDG_RUNTIME_DIR/syncopated-firstboot.lock"
  flock -n 8
  run "$SCRIPT" </dev/null
  exec 8>&-
  [ "$status" -eq 0 ]
  [[ $output == *"already running"* ]]
  ! grep -q '^gum choose' "$STUB_LOG"
}
