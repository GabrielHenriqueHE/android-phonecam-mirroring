"""Conexão TCP com o celular: recebe, decodifica e publica o último frame pronto."""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .compose import compose
from .decoder import H264Decoder
from .discovery import Endpoint
from .protocol import Config, Frame, ProtocolError, read_handshake, read_packet

log = logging.getLogger(__name__)

EndpointProvider = Callable[[], Endpoint | None]


@dataclass
class StreamOptions:
    out_width: int
    out_height: int
    rotation_override: int | None = None  # None = usa a rotação enviada pelo celular
    mirror: bool = False
    connect_timeout: float = 5.0
    read_timeout: float = 5.0  # sem dados por esse tempo = celular sumiu
    reconnect_delay: float = 2.0


class LatestFrame:
    """Slot thread-safe com o último frame composto (descarta os antigos)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._img: np.ndarray | None = None
        self._ts = 0.0

    def put(self, img: np.ndarray) -> None:
        with self._lock:
            self._img, self._ts = img, time.monotonic()

    def get(self, max_age: float) -> np.ndarray | None:
        with self._lock:
            if self._img is None or time.monotonic() - self._ts > max_age:
                return None
            return self._img


class StreamClient(threading.Thread):
    def __init__(
        self,
        endpoint_provider: EndpointProvider,
        options: StreamOptions,
        latest: LatestFrame,
        stop: threading.Event,
    ) -> None:
        super().__init__(name="phonecam-client", daemon=True)
        self._provider = endpoint_provider
        self._opt = options
        self._latest = latest
        self._stop = stop
        self._decoder = H264Decoder()
        self._rotation = 0
        self.connected = threading.Event()
        self.frames_decoded = 0

    # ------------------------------------------------------------------ loop
    def run(self) -> None:
        while not self._stop.is_set():
            endpoint = self._provider()
            if endpoint is None:
                log.info("celular não encontrado; tentando de novo em %.0fs", self._opt.reconnect_delay)
                self._stop.wait(self._opt.reconnect_delay)
                continue
            try:
                self._session(endpoint)
            except (OSError, EOFError, ProtocolError) as exc:
                if not self._stop.is_set():
                    log.warning("conexão com %s:%d caiu: %s", endpoint.host, endpoint.port, exc)
            finally:
                self.connected.clear()
            self._stop.wait(self._opt.reconnect_delay)

    def _session(self, ep: Endpoint) -> None:
        log.info("conectando em %s (%s:%d)...", ep.name, ep.host, ep.port)
        with socket.create_connection((ep.host, ep.port), timeout=self._opt.connect_timeout) as sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(self._opt.read_timeout)
            stream = sock.makefile("rb", buffering=256 * 1024)
            read_handshake(stream)
            self._decoder.reset()
            self.connected.set()
            log.info("conectado")

            stats_t, stats_n = time.monotonic(), 0
            while not self._stop.is_set():
                packet = read_packet(stream)
                if isinstance(packet, Config):
                    self._on_config(packet)
                elif isinstance(packet, Frame):
                    stats_n += self._on_frame(packet)

                now = time.monotonic()
                if now - stats_t >= 5.0:
                    log.info("%.1f fps recebidos", stats_n / (now - stats_t))
                    stats_t, stats_n = now, 0

    # --------------------------------------------------------------- handlers
    def _on_config(self, cfg: Config) -> None:
        self._rotation = cfg.rotation
        self._decoder.set_codec_config(cfg.codec_config)
        log.info(
            "stream: %dx%d, rotação %d°, câmera %s",
            cfg.width, cfg.height, cfg.rotation, "frontal" if cfg.facing else "traseira",
        )

    def _on_frame(self, fr: Frame) -> int:
        rotation = self._opt.rotation_override if self._opt.rotation_override is not None else self._rotation
        n = 0
        for vf in self._decoder.decode(fr.data, fr.keyframe):
            img = compose(vf, rotation, self._opt.out_width, self._opt.out_height, self._opt.mirror)
            self._latest.put(img)
            n += 1
        self.frames_decoded += n
        return n
