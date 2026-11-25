"""Descoberta do celular na rede local via mDNS/DNS-SD (o app registra _phonecam._tcp)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

log = logging.getLogger(__name__)

SERVICE_TYPE = "_phonecam._tcp.local."


@dataclass(frozen=True)
class Endpoint:
    name: str
    host: str
    port: int


class _Listener(ServiceListener):
    def __init__(self) -> None:
        self.found: list[Endpoint] = []
        self.event = threading.Event()

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name, timeout=3000)
        if not info:
            return
        ipv4 = [a for a in info.parsed_addresses() if ":" not in a]
        if ipv4 and info.port:
            self.found.append(Endpoint(name.removesuffix("." + type_), ipv4[0], info.port))
            self.event.set()

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass


def discover(timeout: float = 5.0) -> Endpoint | None:
    zc = Zeroconf()
    listener = _Listener()
    try:
        ServiceBrowser(zc, SERVICE_TYPE, listener=listener)
        listener.event.wait(timeout)
        return listener.found[0] if listener.found else None
    finally:
        zc.close()
