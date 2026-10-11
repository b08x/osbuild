#!/usr/bin/env bats
# The repo pre-flight in templates/image-builder-build.sh.j2: render the build
# script, stub `sudo` so image-builder is never run, and serve fake repos over
# a local http.server.

ROLE="$BATS_TEST_DIRNAME/../.."

setup() {
  WORK="$BATS_TEST_TMPDIR"
  mkdir -p "$WORK/srv/good/repodata" "$WORK/srv/bad/repodata" "$WORK/bin"
  for r in good bad; do
    echo data >"$WORK/srv/$r/repodata/aaa-primary.xml.gz"
    printf '<repomd><data><location href="repodata/aaa-primary.xml.gz"/></data></repomd>\n' \
      >"$WORK/srv/$r/repodata/repomd.xml"
  done
  rm "$WORK/srv/bad/repodata/aaa-primary.xml.gz"
  printf '#!/bin/sh\necho SUDO "$@" >"%s/sudo.log"\nexit 1\n' "$WORK" >"$WORK/bin/sudo"
  chmod +x "$WORK/bin/sudo"
  (cd "$WORK/srv" && exec python3 -u -m http.server 0 --bind 127.0.0.1 >"$WORK/http.log" 2>&1) &
  HTTP_PID=$!
  for _ in $(seq 50); do
    PORT=$(sed -n 's/.*port \([0-9]*\).*/\1/p' "$WORK/http.log" | head -1)
    [ -n "$PORT" ] && break
    sleep 0.1
  done
}

teardown() { kill "$HTTP_PID" 2>/dev/null || true; }

render() {
  python3 - "$ROLE/templates/image-builder-build.sh.j2" "$WORK/build.sh" "$@" <<'PY'
import sys, jinja2
src, out, *urls = sys.argv[1:]
env = jinja2.Environment(keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)
env.filters["quote"] = lambda v: "'" + str(v).replace("'", "'\\''") + "'"
env.filters["regex_replace"] = lambda v, *a: v
open(out, "w").write(env.from_string(open(src).read()).render(
    osbuild_blueprint_name="t", osbuild_distro="d", osbuild_image_type="image-installer",
    osbuild_arch="x86_64", osbuild_output_dir=".", osbuild_output_filename="t.iso",
    osbuild_extra_repo_urls=urls))
PY
}

@test "consistent repos pass and reach image-builder" {
  render "http://127.0.0.1:$PORT/good/" "http://127.0.0.1:$PORT/good"
  run env PATH="$WORK/bin:$PATH" bash "$WORK/build.sh"
  [[ "$output" == *"Pre-flight: checking 2"* ]]
  [ -e "$WORK/sudo.log" ]
}

@test "a repo whose repomd lists a missing file stops the build before image-builder" {
  render "http://127.0.0.1:$PORT/good" "http://127.0.0.1:$PORT/bad"
  run env PATH="$WORK/bin:$PATH" bash "$WORK/build.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"/bad: repomd.xml lists repodata/aaa-primary.xml.gz but the server does not serve it"* ]]
  [ ! -e "$WORK/sudo.log" ]
}

@test "a repo without repomd.xml stops the build" {
  render "http://127.0.0.1:$PORT/nonexistent"
  run env PATH="$WORK/bin:$PATH" bash "$WORK/build.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"repodata/repomd.xml is not downloadable"* ]]
}

@test "SKIP_REPO_PREFLIGHT=1 skips the check" {
  render "http://127.0.0.1:$PORT/bad"
  run env SKIP_REPO_PREFLIGHT=1 PATH="$WORK/bin:$PATH" bash "$WORK/build.sh"
  [ -e "$WORK/sudo.log" ]
}

@test "no extra repos, no pre-flight block" {
  render
  ! grep -q repo_preflight "$WORK/build.sh"
  bash -n "$WORK/build.sh"
}

play() {
  python3 - "$@" <<'PY' >"$WORK/urls.json"
import json, sys
print(json.dumps({"osbuild_extra_repo_urls": sys.argv[1:]}))
PY
  : >"$WORK/ansible.cfg"
  ANSIBLE_CONFIG="$WORK/ansible.cfg" ANSIBLE_RETRY_FILES_ENABLED=0 \
    ansible-playbook -i "$ROLE/tests/inventory" "$ROLE/tests/validate_repo_preflight.yml" \
    -e "@$WORK/urls.json"
}

@test "play: consistent repos pass, metalinks are skipped" {
  run play "http://127.0.0.1:$PORT/good/" "http://127.0.0.1:$PORT/good" \
    "http://127.0.0.1:$PORT/bad?metalink=1"
  [ "$status" -eq 0 ]
  [[ "$output" == *"1 extra repositories checked"* ]]
}

@test "play: a repomd that lists a missing file fails the play" {
  run play "http://127.0.0.1:$PORT/bad"
  [ "$status" -eq 2 ]
  [[ "$output" == *"/bad/repodata/aaa-primary.xml.gz is listed in repomd.xml but not served"* ]]
}

@test "play: a repo without repomd.xml fails the play" {
  run play "http://127.0.0.1:$PORT/nonexistent"
  [ "$status" -eq 2 ]
  [[ "$output" == *"/nonexistent/repodata/repomd.xml is not downloadable"* ]]
}

@test "script: metalink URLs are not checked" {
  render "http://127.0.0.1:$PORT/bad?metalink=1"
  run env PATH="$WORK/bin:$PATH" bash "$WORK/build.sh"
  [[ "$output" == *"metalink, not checked"* ]]
  [ -e "$WORK/sudo.log" ]
}
