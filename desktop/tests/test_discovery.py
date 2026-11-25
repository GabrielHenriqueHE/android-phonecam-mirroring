import socket

import pytest
from zeroconf import ServiceInfo, Zeroconf

from phonecam.discovery import SERVICE_TYPE, discover


def test_discover_finds_registered_service():
    zc = Zeroconf()
    info = ServiceInfo(
        SERVICE_TYPE, f"PhoneCam-Test.{SERVICE_TYPE}",
        addresses=[socket.inet_aton("127.0.0.1")], port=8787,
    )
    try:
        zc.register_service(info)
    except OSError as exc:  # ambiente sem multicast
        pytest.skip(f"multicast indisponível: {exc}")
    try:
        ep = discover(timeout=5)
        if ep is None:
            pytest.skip("multicast não roteado neste ambiente")
        assert ep.port == 8787
        assert ep.name == "PhoneCam-Test"
    finally:
        zc.unregister_service(info)
        zc.close()
