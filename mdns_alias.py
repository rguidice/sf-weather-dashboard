#!/usr/bin/env python3
"""Publish an mDNS CNAME alias via Avahi's D-Bus API.

Makes 'weather.local' resolve to this machine's hostname.
Uses the org.freedesktop.Avahi.EntryGroup.AddRecord method
documented at https://github.com/avahi/avahi/blob/master/avahi-daemon/org.freedesktop.Avahi.EntryGroup.xml
"""

import signal
import socket
import sys
import time

import dbus

AVAHI_BUS = "org.freedesktop.Avahi"
AVAHI_PATH = "/"
AVAHI_IFACE = "org.freedesktop.Avahi.Server"
ENTRY_GROUP_IFACE = "org.freedesktop.Avahi.EntryGroup"

IFACE_UNSPEC = -1  # all interfaces
PROTO_UNSPEC = -1  # IPv4 + IPv6
DNS_CLASS_IN = 0x01
DNS_TYPE_CNAME = 0x05
TTL = 60

ALIAS = "weather.local"


def encode_dns_name(name):
    """Encode a hostname into DNS wire format (RFC 1035 section 3.1)."""
    parts = name.rstrip(".").split(".")
    result = []
    for part in parts:
        encoded = part.encode("utf-8")
        result.append(bytes([len(encoded)]))
        result.append(encoded)
    result.append(b"\x00")
    return b"".join(result)


def publish():
    hostname = socket.gethostname() + ".local"
    rdata = encode_dns_name(hostname)

    bus = dbus.SystemBus()
    server = dbus.Interface(bus.get_object(AVAHI_BUS, AVAHI_PATH), AVAHI_IFACE)
    group = dbus.Interface(
        bus.get_object(AVAHI_BUS, server.EntryGroupNew()),
        ENTRY_GROUP_IFACE,
    )

    group.AddRecord(
        IFACE_UNSPEC,
        PROTO_UNSPEC,
        dbus.UInt32(0),       # flags
        ALIAS,
        DNS_CLASS_IN,
        DNS_TYPE_CNAME,
        TTL,
        dbus.Array(rdata, signature="y"),
    )
    group.Commit()
    print(f"Publishing {ALIAS} -> {hostname}")

    # Keep the process alive so the record stays published
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    publish()
