# shellcheck shell=bash
# Shared helpers for test stubs. Each stub logs its argv to $STUB_LOG.

stub_log() {
  printf '%s\n' "$*" >>"${STUB_LOG:?STUB_LOG unset}"
}

# Print and remove the first line of queue file $1. Fails when it is empty.
stub_pop() {
  local queue=$1 line
  [[ -s $queue ]] || return 1
  IFS= read -r line <"$queue"
  sed -i 1d "$queue"
  printf '%s\n' "$line"
}
