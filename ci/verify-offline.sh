#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "offline verification accepts no shell command arguments" >&2
  exit 2
fi
if [[ -z "${HARNESS_TASK_PACKET:-}" || ! -f "${HARNESS_TASK_PACKET}" ]]; then
  echo "HARNESS_TASK_PACKET must name a readable packet YAML file" >&2
  exit 2
fi

ci_dir="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
repo_root="$(CDPATH='' cd -- "${ci_dir}/.." && pwd -P)"
runner="${ci_dir}/run_packet_argv.py"
session_id="ind-001-$PPID-$$"
packet_dir="$(CDPATH='' cd -- "$(dirname -- "$HARNESS_TASK_PACKET")" && pwd -P)"
packet_path="${packet_dir}/$(basename -- "$HARNESS_TASK_PACKET")"
export PATH="${ci_dir}:${PATH}"
export SOURCE_DATE_EPOCH="946684800"

if [[ "${HARNESS_OFFLINE_ENFORCED:-0}" == "1" ]]; then
  [[ -n "${HARNESS_OFFLINE_BACKEND:-}" && -n "${HARNESS_OFFLINE_SESSION_ID:-}" ]] \
    || { echo "trusted outer isolation must name its backend and session" >&2; exit 2; }
  for offline_setting in UV_OFFLINE UV_FROZEN UV_NO_SYNC; do
    [[ "${!offline_setting:-}" == "1" ]] || { echo "trusted isolation requires ${offline_setting}=1" >&2; exit 2; }
  done
  cd "$repo_root"
  exec python3 "$runner"
fi

# shellcheck source=warm-source-isolation.sh
source "${ci_dir}/warm-source-isolation.sh"
harness_load_warm_source_roots

case "$(uname -s)" in
  Darwin)
    [[ -x /usr/bin/sandbox-exec ]] || { echo "offline verification refused: sandbox-exec unavailable" >&2; exit 2; }
    profile='(version 1) (allow default) (deny network*) (deny file-write* (literal (param "PACKET_PATH")))'
    parameters=(-D "PACKET_PATH=${packet_path}")
    root_index=0
    for warm_root in "${warm_source_roots[@]}"; do
      [[ "$warm_root" == "$HARNESS_WARM_SOURCE_SENTINEL" ]] && continue
      name="WARM_ROOT_${root_index}"
      parameters+=(-D "${name}=${warm_root}")
      profile+=" (deny file-read* (subpath (param \"${name}\"))) (deny file-write* (subpath (param \"${name}\")))"
      root_index=$((root_index + 1))
    done
    harness_scrub_warm_source_environment
    cd "$repo_root"
    exec /usr/bin/sandbox-exec "${parameters[@]}" -p "$profile" env \
      PATH="$PATH" SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
      HARNESS_TASK_PACKET="$packet_path" HARNESS_OFFLINE_ENFORCED=1 \
      HARNESS_OFFLINE_BACKEND=darwin-sandbox HARNESS_OFFLINE_SESSION_ID="$session_id" \
      UV_OFFLINE=1 UV_FROZEN=1 UV_NO_SYNC=1 python3 "$runner"
    ;;
  Linux)
    command -v firejail >/dev/null 2>&1 || { echo "offline verification refused: firejail is required" >&2; exit 2; }
    arguments=(--quiet --net=none "--read-only=${packet_path}")
    for warm_root in "${warm_source_roots[@]}"; do
      [[ "$warm_root" == "$HARNESS_WARM_SOURCE_SENTINEL" ]] && continue
      arguments+=("--blacklist=${warm_root}" "--read-only=${warm_root}")
    done
    harness_scrub_warm_source_environment
    cd "$repo_root"
    exec firejail "${arguments[@]}" env \
      PATH="$PATH" SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
      HARNESS_TASK_PACKET="$packet_path" HARNESS_OFFLINE_ENFORCED=1 \
      HARNESS_OFFLINE_BACKEND=linux-firejail HARNESS_OFFLINE_SESSION_ID="$session_id" \
      UV_OFFLINE=1 UV_FROZEN=1 UV_NO_SYNC=1 python3 "$runner"
    ;;
  *)
    echo "offline verification refused: unsupported isolation platform" >&2
    exit 2
    ;;
esac

