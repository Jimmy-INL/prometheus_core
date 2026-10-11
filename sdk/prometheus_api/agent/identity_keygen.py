# This file is part of Prometheus
# https://inl.gov/super-intelligence/prometheus/
#
# Copyright 2026 Battelle Energy Alliance, LLC
# All rights reserved, see NOTICE.txt for full restrictions
# https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
#
# Licensed under the MIT License, please see LICENSE for details
# https://github.com/idaholab/prometheus_core/blob/main/LICENSE
#
# SPDX-License-Identifier: MIT

"""Generate an RSA keypair for the multi-user identity plane (see identity.py).

Ships in the ``prometheus_api`` package, so it is available inside every agent
container (built ``FROM`` the base image) with no extra installation — including
third-party agents built from the ``agent-template/`` scaffold.

Usage
-----
As a console script (installed by the ``prometheus-api`` package)::

    prometheus-identity-keygen                       # print PEM + .env snippet
    prometheus-identity-keygen --out-dir ./keys       # write PEM files instead

As a module::

    python -m prometheus_api.agent.identity_keygen --out-dir ./keys

Programmatically::

    from prometheus_api.agent.identity_keygen import generate_keypair
    private_pem, public_pem = generate_keypair()
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path


def generate_keypair(key_size: int = 4096) -> tuple[str, str]:
    """Generate an RSA keypair and return ``(private_pem, public_pem)``.

    Both are PEM-encoded strings, unencrypted (no passphrase) — suitable for
    ``USER_IDENTITY_PRIVATE_KEY`` / ``USER_IDENTITY_PUBLIC_KEY``.

    Args:
        key_size: RSA modulus size in bits.  4096 (default) is a comfortable
            production margin; 2048 is the practical minimum for RS256.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    if key_size < 2048:
        raise ValueError("key_size must be at least 2048 bits for RS256")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _write_key_file(path: Path, content: str, *, private: bool) -> None:
    path.write_text(content, encoding="utf-8")
    if private:
        # Owner read/write only — this is signing material.
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _env_escaped(pem: str) -> str:
    """Format a PEM block as a single-line, double-quoted .env value."""
    return '"' + pem.replace("\n", "\\n") + '"'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prometheus-identity-keygen",
        description="Generate an RS256 keypair for the Prometheus multi-user identity plane.",
    )
    parser.add_argument(
        "--key-size",
        type=int,
        default=4096,
        help="RSA key size in bits (default: 4096; minimum: 2048).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Directory to write identity_private.pem and identity_public.pem into. "
            "If omitted, both keys and a ready-to-paste .env snippet are printed to stdout."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing key files in --out-dir if present.",
    )
    args = parser.parse_args(argv)

    private_pem, public_pem = generate_keypair(key_size=args.key_size)

    if args.out_dir is None:
        print("# USER_IDENTITY_PRIVATE_KEY — backend/minting side ONLY. Never share.")
        print(f"USER_IDENTITY_PRIVATE_KEY={_env_escaped(private_pem)}")
        print()
        print("# USER_IDENTITY_PUBLIC_KEY — safe to distribute to every verifying agent.")
        print(f"USER_IDENTITY_PUBLIC_KEY={_env_escaped(public_pem)}")
        return 0

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / "identity_private.pem"
    public_path = out_dir / "identity_public.pem"

    for path in (private_path, public_path):
        if path.exists() and not args.force:
            print(f"error: {path} already exists (use --force to overwrite)", file=sys.stderr)
            return 1

    _write_key_file(private_path, private_pem, private=True)
    _write_key_file(public_path, public_pem, private=False)

    print(f"Wrote {private_path} (private — backend only, keep secret)")
    print(f"Wrote {public_path} (public — distribute to every agent that verifies tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
