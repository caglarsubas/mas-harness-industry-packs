.DEFAULT_GOAL := help

.PHONY: help prefetch pack-framework-test build-reproducible zero-bill

help prefetch pack-framework-test build-reproducible zero-bill:
	@python3 ci/run_make_target.py "$@"

%:
	@python3 ci/run_make_target.py "$@"

