"""Sobe o celular falso de verdade (subprocess, TCP local) e confere a imagem que sai."""

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from phonecam.app import run
from phonecam.client import StreamOptions
from phonecam.compose import PLACEHOLDER_RGB
from phonecam.discovery import Endpoint
from phonecam.sink import NullSink

FAKE = Path(__file__).resolve().parents[1] / "tools" / "fake_phone.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_fake(port: int, *extra: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(FAKE), "--port", str(port), *extra],
        stdout=subprocess.PIPE, text=True,
    )
    assert "ouvindo" in proc.stdout.readline()
    return proc


def _run_bridge(port, seconds, sink, **opt):
    stop = threading.Event()
    ep = Endpoint("fake", "127.0.0.1", port)
    options = StreamOptions(out_width=sink.width, out_height=sink.height, reconnect_delay=0.3, **opt)
    result = {}

    def target():
        result["client"] = run(lambda: ep, sink, options, stop)

    t = threading.Thread(target=target)
    t.start()
    time.sleep(seconds)
    stop.set()
    t.join(5)
    return result["client"]


def test_stream_rotated_reaches_virtual_cam():
    port = _free_port()
    fake = _start_fake(port, "--rotation", "90")
    try:
        sink = NullSink(1280, 720, 30)
        client = _run_bridge(port, 2.5, sink)
    finally:
        fake.terminate()
        fake.wait()

    assert client.frames_decoded > 30, client.frames_decoded
    assert sink.frames_sent > 30
    img = sink.last
    assert img.shape == (720, 1280, 3)
    # retrato 480x640 -> 540x720 centralizado: barras pretas dos lados
    assert not img[:, :350].any()
    # marcador vermelho foi para o canto superior DIREITO da área útil
    cols = np.where(img.any(axis=(0, 2)))[0]
    px = img[10, cols[-1] - 10].astype(int)
    assert px[0] > 180 and px[1] < 80 and px[2] < 80, px


def test_placeholder_then_reconnect():
    port = _free_port()
    sink = NullSink(320, 240, 30)
    stop = threading.Event()
    ep = Endpoint("fake", "127.0.0.1", port)
    options = StreamOptions(out_width=320, out_height=240, reconnect_delay=0.3)
    t = threading.Thread(target=run, args=(lambda: ep, sink, options, stop), kwargs={"stale_after": 0.3})
    t.start()
    try:
        time.sleep(0.8)  # sem celular: deve mandar o placeholder
        assert sink.frames_sent > 5
        assert tuple(sink.last[0, 0]) == PLACEHOLDER_RGB

        fake = _start_fake(port)  # celular "aparece"
        try:
            deadline = time.time() + 5
            while tuple(sink.last[0, 0]) == PLACEHOLDER_RGB and time.time() < deadline:
                time.sleep(0.05)
            assert tuple(sink.last[0, 0]) != PLACEHOLDER_RGB, "nunca recebeu vídeo"
        finally:
            fake.terminate()  # celular "some" (app fechado / Wi-Fi caiu)
            fake.wait()

        time.sleep(1.0)  # -> volta ao placeholder, sem travar no último frame
        assert tuple(sink.last[0, 0]) == PLACEHOLDER_RGB

        fake = _start_fake(port)  # e reconecta sozinho quando o celular volta
        try:
            deadline = time.time() + 5
            while tuple(sink.last[0, 0]) == PLACEHOLDER_RGB and time.time() < deadline:
                time.sleep(0.05)
            assert tuple(sink.last[0, 0]) != PLACEHOLDER_RGB, "não reconectou"
        finally:
            fake.terminate()
            fake.wait()
    finally:
        stop.set()
        t.join(5)
