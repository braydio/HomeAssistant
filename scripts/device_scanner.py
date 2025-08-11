#!/usr/bin/env python3
"""Scan the local network for active devices.

The script attempts TCP connections to a specified port on every host in a
network range. Hosts that respond are reported as available devices.
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import List

DEFAULT_PORT = 80
DEFAULT_NETWORK = "192.168.1.0/24"


def _probe(host: str, port: int, timeout: float) -> bool:
    """Return True if the host responds on the given port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def scan(network: str, port: int = DEFAULT_PORT, timeout: float = 0.5) -> List[str]:
    """Scan ``network`` for responsive hosts on ``port``.

    Args:
        network: CIDR range to scan, e.g. ``192.168.1.0/24``.
        port: TCP port to probe. Defaults to 80.
        timeout: Seconds to wait for each connection.

    Returns:
        A list of hosts that responded.
    """

    net = ipaddress.ip_network(network, strict=False)
    hosts = [str(ip) for ip in net.hosts()]
    responsive: List[str] = []

    def worker(ip: str) -> None:
        if _probe(ip, port, timeout):
            responsive.append(ip)

    with ThreadPoolExecutor(max_workers=64) as executor:
        for ip in hosts:
            executor.submit(worker, ip)
    return responsive


def main() -> None:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Scan for active network devices.")
    parser.add_argument(
        "--network",
        default=DEFAULT_NETWORK,
        help="Network range in CIDR notation (default: %(default)s)",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="TCP port to probe"
    )
    parser.add_argument(
        "--timeout", type=float, default=0.5, help="Socket timeout in seconds"
    )
    args = parser.parse_args()

    active = scan(args.network, args.port, args.timeout)
    if not active:
        print("No active hosts found")
    else:
        for ip in sorted(active):
            print(ip)


if __name__ == "__main__":
    main()
