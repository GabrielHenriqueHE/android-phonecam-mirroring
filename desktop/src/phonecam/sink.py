"""Destinos dos frames: webcam virtual (v4l2loopback) ou nulo (debug/testes)."""

from __future__ import annotations

import sys
import time
from typing import Protocol

import numpy as np


class Sink(Protocol):
    width: int
    height: int

    def send(self, img: np.ndarray) -> None: ...
    def sleep_until_next_frame(self) -> None: ...
    def close(self) -> None: ...


class VirtualCamSink:
    def __init__(self, width: int, height: int, fps: float, device: str | None) -> None:
        import pyvirtualcam  # import tardio: o sink nulo não precisa do driver

        backend = "v4l2loopback" if sys.platform.startswith("linux") else None
        self._cam = pyvirtualcam.Camera(
            width, height, fps, fmt=pyvirtualcam.PixelFormat.RGB, device=device, backend=backend
        )
        self.width, self.height = width, height
        self.device = self._cam.device

    def send(self, img: np.ndarray) -> None:
        self._cam.send(img)

    def sleep_until_next_frame(self) -> None:
        self._cam.sleep_until_next_frame()

    def close(self) -> None:
        self._cam.close()


class NullSink:
    """Descarta os frames, mas guarda o último e conta quantos chegaram."""

    def __init__(self, width: int, height: int, fps: float) -> None:
        self.width, self.height = width, height
        self.device = "null"
        self._period = 1.0 / fps
        self._next = time.monotonic()
        self.frames_sent = 0
        self.last: np.ndarray | None = None

    def send(self, img: np.ndarray) -> None:
        assert img.shape == (self.height, self.width, 3), img.shape
        self.frames_sent += 1
        self.last = img

    def sleep_until_next_frame(self) -> None:
        self._next += self._period
        delay = self._next - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            self._next = time.monotonic()

    def close(self) -> None:
        pass
