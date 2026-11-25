"""Junta tudo: cliente de rede numa thread, webcam virtual no ritmo fixo na principal."""

from __future__ import annotations

import logging
import threading

from .client import EndpointProvider, LatestFrame, StreamClient, StreamOptions
from .compose import placeholder
from .sink import Sink

log = logging.getLogger(__name__)


def run(
    provider: EndpointProvider,
    sink: Sink,
    options: StreamOptions,
    stop: threading.Event,
    stale_after: float = 1.0,
) -> StreamClient:
    """Alimenta o sink no FPS dele até `stop` ser setado.

    A webcam virtual recebe frames sempre — mesmo sem celular (tela cinza). Assim o
    Meet não "perde" a câmera quando o Wi-Fi oscila ou o app é reaberto.
    """
    latest = LatestFrame()
    client = StreamClient(provider, options, latest, stop)
    client.start()

    idle = placeholder(sink.width, sink.height)
    try:
        while not stop.is_set():
            img = latest.get(max_age=stale_after)
            sink.send(idle if img is None else img)
            sink.sleep_until_next_frame()
    finally:
        stop.set()
        client.join(timeout=2)
        sink.close()
    return client
