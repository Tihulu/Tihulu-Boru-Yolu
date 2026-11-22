#!/usr/bin/env python3
"""M09 listener proof: Boru's only surface is loopback, and it is released.

Runs the loopback dashboard, verifies the address it actually bound is a numeric
loopback address (and not a wildcard), verifies a public bind is refused, then
stops it and verifies the port is released and no thread survives. The output is
a sanitized summary: an address class and a port number, never a path, a token
or a host inventory.

Usage: python3 scripts/listener_check.py [--json]
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boru.config import CoreConfig, ProviderConfig  # noqa: E402
from boru.core import BoruCore  # noqa: E402
from boru.dashboard import BoruDashboard  # noqa: E402


def _classify(address) -> str:
    """One of loopback / link-local / private / public, never the raw address."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return "unknown"
    if parsed.is_loopback:
        return "loopback"
    if parsed.is_link_local:
        return "link-local"
    if parsed.is_private:
        return "private"
    return "public"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M09 listener proof")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    evidence = {}

    import threading

    baseline = sum(1 for thread in threading.enumerate() if thread.is_alive())
    engine = BoruCore(CoreConfig(providers=(ProviderConfig(kind="mock"),)))
    try:
        dashboard = BoruDashboard(engine)
        host, port = dashboard.start()
        evidence["bound_address_class"] = _classify(host)
        evidence["bound_is_loopback"] = _classify(host) == "loopback"
        evidence["port_bound"] = isinstance(port, int) and port > 0
        # a public bind is refused by construction, not by convention
        try:
            BoruDashboard(engine, host="0.0.0.0")
            evidence["public_bind_refused"] = False
        except ValueError:
            evidence["public_bind_refused"] = True
        dashboard.stop()
        # the port is released: nothing keeps listening after stop
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", port))
            evidence["port_released_after_stop"] = True
        except OSError:
            evidence["port_released_after_stop"] = False
        finally:
            probe.close()
        # no Boru-owned thread survives the stop: the live count returns to the
        # count this process had before the dashboard started
        import threading

        evidence["threads_before_start"] = baseline
        evidence["threads_after_stop"] = sum(
            1 for thread in threading.enumerate() if thread.is_alive())
        evidence["no_thread_survives_stop"] = (
            evidence["threads_after_stop"] <= baseline)
    finally:
        engine.close()

    ok = (evidence["bound_is_loopback"] and evidence["public_bind_refused"]
          and evidence["port_released_after_stop"] and evidence["port_bound"]
          and evidence["no_thread_survives_stop"])
    payload = dict(evidence, ok=ok, live_acceptance="HOLD")
    if args.json:
        sys.stdout.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    else:
        for key, value in payload.items():
            sys.stdout.write("{}: {}\n".format(key, value))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
