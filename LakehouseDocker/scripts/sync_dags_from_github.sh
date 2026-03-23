#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPO_URL="${REPO_URL:-https://github.com/shaoniandelilian/BigHealthDataWarehouse.git}"
REPO_BRANCH="${REPO_BRANCH:-}"
REPO_DIR="${REPO_DIR:-$SCRIPT_DIR/.cache/BigHealthDataWarehouse}"
STATE_DIR="${STATE_DIR:-$SCRIPT_DIR/.state}"
LOCAL_DAGS_SUBDIR="${LOCAL_DAGS_SUBDIR:-DAGs}"
NAMESPACE="${NAMESPACE:-lakehouse}"
POD_SELECTOR="${POD_SELECTOR:-app=airflow}"
CONTAINER_NAME="${CONTAINER_NAME:-scheduler}"
REMOTE_DAGS_DIR="${REMOTE_DAGS_DIR:-/opt/airflow/dags}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-30}"
CLEAR_TARGET="${CLEAR_TARGET:-1}"
RUN_ONCE="${RUN_ONCE:-0}"
SYNC_ON_SAME_REVISION="${SYNC_ON_SAME_REVISION:-1}"

LAST_SYNC_FILE="$STATE_DIR/last_synced_commit"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "missing required command: $1"
    exit 1
  fi
}

init_dirs() {
  mkdir -p "$(dirname "$REPO_DIR")" "$STATE_DIR"
}

clone_repo_if_needed() {
  if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
    return
  fi

  rm -rf "$REPO_DIR"
  if [ -n "$REPO_BRANCH" ]; then
    git clone --branch "$REPO_BRANCH" --single-branch "$REPO_URL" "$REPO_DIR"
  else
    git clone "$REPO_URL" "$REPO_DIR"
  fi
}

update_repo() {
  if [ -n "$REPO_BRANCH" ]; then
    git -C "$REPO_DIR" fetch --prune origin "$REPO_BRANCH"
    git -C "$REPO_DIR" checkout -B "$REPO_BRANCH" "origin/$REPO_BRANCH"
    return
  fi

  local current_branch
  current_branch="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)"
  git -C "$REPO_DIR" fetch --prune origin "$current_branch"
  git -C "$REPO_DIR" reset --hard "origin/$current_branch"
}

resolve_local_dags_dir() {
  local candidate

  for candidate in \
    "$REPO_DIR/$LOCAL_DAGS_SUBDIR" \
    "$REPO_DIR/DAGs" \
    "$REPO_DIR/dags"
  do
    if [ -d "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

get_running_pod() {
  kubectl -n "$NAMESPACE" get pod \
    -l "$POD_SELECTOR" \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}'
}

prepare_remote_dir() {
  local pod="$1"

  kubectl -n "$NAMESPACE" exec "$pod" -c "$CONTAINER_NAME" -- \
    sh -c "mkdir -p '$REMOTE_DAGS_DIR'"

  if [ "$CLEAR_TARGET" = "1" ]; then
    kubectl -n "$NAMESPACE" exec "$pod" -c "$CONTAINER_NAME" -- \
      sh -c "find '$REMOTE_DAGS_DIR' -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +"
  fi
}

sync_dags_to_scheduler() {
  local pod="$1"
  local local_dags_dir="$2"

  prepare_remote_dir "$pod"
  tar -C "$local_dags_dir" -cf - . | \
    kubectl -n "$NAMESPACE" exec -i "$pod" -c "$CONTAINER_NAME" -- \
      tar -xf - -C "$REMOTE_DAGS_DIR" --no-same-owner --no-same-permissions
}

current_revision() {
  git -C "$REPO_DIR" rev-parse HEAD
}

last_synced_revision() {
  if [ -f "$LAST_SYNC_FILE" ]; then
    cat "$LAST_SYNC_FILE"
  fi
}

run_cycle() {
  local local_dags_dir
  local pod
  local revision
  local previous_revision

  clone_repo_if_needed
  update_repo
  revision="$(current_revision)"
  previous_revision="$(last_synced_revision || true)"

  if ! local_dags_dir="$(resolve_local_dags_dir)"; then
    log "cannot find DAG directory under $REPO_DIR"
    return 1
  fi

  pod="$(get_running_pod)"
  if [ -z "$pod" ]; then
    log "cannot find a running pod for selector $POD_SELECTOR in namespace $NAMESPACE"
    return 1
  fi

  if [ "$revision" = "$previous_revision" ] && [ "$SYNC_ON_SAME_REVISION" != "1" ]; then
    log "repository unchanged at $revision; skip sync"
    return 0
  fi

  log "syncing $local_dags_dir to $pod:$REMOTE_DAGS_DIR from commit $revision"
  sync_dags_to_scheduler "$pod" "$local_dags_dir"
  printf '%s\n' "$revision" > "$LAST_SYNC_FILE"
  log "sync completed"
}

main() {
  require_cmd git
  require_cmd kubectl
  require_cmd tar
  init_dirs

  while true; do
    if ! run_cycle; then
      log "sync cycle failed; will retry after ${INTERVAL_SECONDS}s"
    fi

    if [ "$RUN_ONCE" = "1" ]; then
      break
    fi

    sleep "$INTERVAL_SECONDS"
  done
}

main "$@"
