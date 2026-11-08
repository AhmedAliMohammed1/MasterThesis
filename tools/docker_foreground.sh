#!/usr/bin/env bash
# Source this helper. Stop only the ID created by this run, never a raced name.
pp_stop_owned_container() {
  trap '' INT TERM
  if [[ -n ${pp_docker_pid:-} ]]; then
    for ((pp_attempt=0; pp_attempt<20; ++pp_attempt)); do
      [[ -s $pp_cidfile ]] && break
      kill -0 "$pp_docker_pid" 2>/dev/null || break
      sleep 0.1
    done
  fi
  local owned_id=''
  [[ ! -s $pp_cidfile ]] || read -r owned_id < "$pp_cidfile" || true
  if [[ $owned_id =~ ^[a-f0-9]{12,64}$ ]]; then
    echo 'Stopping this container; allow up to 8 seconds for shutdown.' >&2
    docker stop --time 8 "$owned_id" >/dev/null 2>&1 || true
  fi
  if [[ -n ${pp_docker_pid:-} ]]; then
    kill -TERM "$pp_docker_pid" 2>/dev/null || true
    wait "$pp_docker_pid" 2>/dev/null || true
  fi
  rm -f -- "$pp_cidfile"
  rmdir -- "$pp_cid_dir"
}

pp_run_container() {
  local pp_cidfile pp_cid_dir pp_docker_pid='' pp_status=0 pp_attempt
  # Private directory prevents another local process from supplying a fake ID
  # between creation of the temporary path and Docker's cidfile write.
  pp_cid_dir=$(mktemp -d "${TMPDIR:-/tmp}/pp-container.XXXXXXXX")
  pp_cidfile="$pp_cid_dir/id"
  trap pp_stop_owned_container EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  # Bash wait is interruptible even when container children ignore SIGINT.
  docker run --cidfile "$pp_cidfile" --sig-proxy=false "$@" &
  pp_docker_pid=$!
  wait "$pp_docker_pid" || pp_status=$?
  pp_stop_owned_container
  trap - EXIT INT TERM
  return "$pp_status"
}
