#!/usr/bin/env bash

HARNESS_WARM_SOURCE_SENTINEL="__HARNESS_NO_WARM_SOURCES__"
warm_source_roots=()

harness_load_warm_source_roots() {
  if [[ -z "${HARNESS_WARM_SOURCE_ROOTS:-}" ]]; then
    echo "offline verification refused: HARNESS_WARM_SOURCE_ROOTS is required" >&2
    return 2
  fi
  while IFS= read -r warm_root; do
    [[ -n "$warm_root" ]] || continue
    if [[ "$warm_root" == "$HARNESS_WARM_SOURCE_SENTINEL" ]]; then
      warm_source_roots+=("$warm_root")
      continue
    fi
    if [[ "$warm_root" != /* || ! -e "$warm_root" ]]; then
      echo "offline verification refused: warm root must be an existing absolute path" >&2
      return 2
    fi
    canonical_root="$(CDPATH='' cd -- "$warm_root" && pwd -P)"
    [[ "$canonical_root" != "/" ]] || { echo "offline verification refused: broad warm root" >&2; return 2; }
    warm_source_roots+=("$canonical_root")
  done <<< "$HARNESS_WARM_SOURCE_ROOTS"
  [[ "${#warm_source_roots[@]}" -gt 0 ]] || { echo "offline verification refused: empty warm root inventory" >&2; return 2; }
}

harness_scrub_warm_source_environment() {
  unset HARNESS_WARM_SOURCE_ROOTS
  unset SSH_AUTH_SOCK KUBECONFIG DOCKER_HOST GOOGLE_APPLICATION_CREDENTIALS AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
}

