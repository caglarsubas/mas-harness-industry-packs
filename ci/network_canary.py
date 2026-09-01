#!/usr/bin/env python3
"""Prove that the enclosing operating-system sandbox denies outbound egress."""

from __future__ import annotations

import errno
import socket
import sys


def main() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        probe.connect(("203.0.113.1", 9))
    except OSError as exc:
        if exc.errno in {errno.EPERM, errno.EACCES}:
            print(f"offline network canary: outbound egress denied with errno={exc.errno}")
            return 0
        print(f"offline network canary failed closed: denial was not OS-enforced ({exc})", file=sys.stderr)
        return 2
    finally:
        probe.close()
    print("offline network canary failed: outbound connection was not denied", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

