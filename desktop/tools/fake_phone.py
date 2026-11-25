#!/usr/bin/env python3
"""Celular falso: serve um padrão de teste em H.264 usando o mesmo protocolo do app.

Útil para desenvolver/testar o desktop sem o Android:

    python tools/fake_phone.py --rotation 90 --mdns
    phonecam --null            # ou phonecam --host 127.0.0.1
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import av
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from phonecam.protocol import (  # noqa: E402
    FACING_FRONT, Config, Frame, encode_config, encode_frame, encode_handshake,
)


def test_pattern(width: int, height: int) -> Iterator[np.ndarray]:
    """Gradiente + barra que anda + quadrado vermelho no canto superior esquerdo
    (o quadrado deixa a orientação conferível)."""
    yy, xx = np.mgrid[0:height, 0:width]
    base = np.stack([(xx * 255 // width), (yy * 255 // height), np.full_like(xx, 128)], -1).astype(np.uint8)
    i = 0
    while True:
        img = base.copy()
        x = (i * 8) % width
        img[:, x:x + 16] = 255
        img[: height // 6, : width // 6] = (255, 0, 0)
        yield img
        i += 1


def encoder(width: int, height: int, fps: int) -> av.VideoCodecContext:
    ctx = av.CodecContext.create("libx264", "w")
    ctx.width, ctx.height = width, height
    ctx.pix_fmt = "yuv420p"
    ctx.framerate = Fraction(fps, 1)
    ctx.time_base = Fraction(1, fps)
    ctx.gop_size = fps  # keyframe a cada 1s, igual ao app
    ctx.max_b_frames = 0
    # Como no MediaCodec: SPS/PPS separados (extradata), fora dos frames.
    ctx.flags |= av.codec.context.Flags.global_header
    ctx.options = {"preset": "ultrafast", "tune": "zerolatency", "repeat-headers": "0"}
    ctx.open()
    return ctx


def serve_client(conn: socket.socket, args: argparse.Namespace, stop: threading.Event) -> None:
    w, h, fps = args.width, args.height, args.fps
    enc = encoder(w, h, fps)
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    conn.sendall(encode_handshake())
    conn.sendall(encode_config(Config(w, h, args.rotation, FACING_FRONT, bytes(enc.extradata or b""))))

    period, t0 = 1.0 / fps, time.monotonic()
    for i, rgb in enumerate(test_pattern(w, h)):
        if stop.is_set() or (args.frames and i >= args.frames):
            break
        vf = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(format="yuv420p")
        vf.pts = i
        for pkt in enc.encode(vf):
            conn.sendall(encode_frame(Frame(pkt.is_keyframe, int(i * period * 1e6), bytes(pkt))))
        delay = t0 + (i + 1) * period - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--rotation", type=int, default=0, choices=[0, 90, 180, 270])
    p.add_argument("--frames", type=int, default=0, help="para depois de N frames (0 = infinito)")
    p.add_argument("--mdns", action="store_true", help="anuncia _phonecam._tcp como o app faz")
    args = p.parse_args()

    zc = None
    if args.mdns:
        from zeroconf import ServiceInfo, Zeroconf
        zc = Zeroconf()
        zc.register_service(ServiceInfo(
            "_phonecam._tcp.local.", "FakePhone._phonecam._tcp.local.",
            addresses=[socket.inet_aton("127.0.0.1")], port=args.port,
        ))

    stop = threading.Event()
    with socket.create_server(("0.0.0.0", args.port), reuse_port=False) as srv:
        print(f"celular falso ouvindo na porta {args.port}", flush=True)
        try:
            while True:
                conn, addr = srv.accept()
                print(f"cliente {addr[0]} conectado", flush=True)
                with conn:
                    try:
                        serve_client(conn, args, stop)
                    except (BrokenPipeError, ConnectionResetError):
                        print("cliente desconectou", flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            if zc:
                zc.close()


if __name__ == "__main__":
    main()
