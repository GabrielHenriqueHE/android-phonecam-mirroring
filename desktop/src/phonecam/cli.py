"""phonecam — usa a câmera do celular como webcam no Linux."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from . import __version__
from .app import run
from .client import StreamOptions
from .discovery import Endpoint, discover

DEFAULT_PORT = 8787

log = logging.getLogger("phonecam")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="phonecam", description=__doc__)
    p.add_argument("--host", help="IP do celular (padrão: descobre sozinho via mDNS)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--device", default="/dev/video10", help="dispositivo v4l2loopback (padrão: %(default)s)")
    p.add_argument("--size", default="1280x720", help="resolução da webcam virtual (padrão: %(default)s)")
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument(
        "--rotate", choices=["auto", "0", "90", "180", "270"], default="auto",
        help="força a rotação (horária); 'auto' usa a que o celular informa",
    )
    p.add_argument("--mirror", action="store_true", help="espelha horizontalmente")
    p.add_argument("--null", action="store_true", help="não abre webcam virtual (só testa a recepção)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args(argv)


def _provider(args: argparse.Namespace):
    if args.host:
        fixed = Endpoint(args.host, args.host, args.port)
        return lambda: fixed

    def find() -> Endpoint | None:
        log.info("procurando o celular na rede (mDNS)...")
        return discover(timeout=5.0)

    return find


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        log.error("--size inválido: %r (use LARGURAxALTURA, ex. 1280x720)", args.size)
        return 2

    if args.null:
        from .sink import NullSink
        sink = NullSink(width, height, args.fps)
    else:
        from .sink import VirtualCamSink
        try:
            sink = VirtualCamSink(width, height, args.fps, args.device)
        except Exception as exc:  # pyvirtualcam lança RuntimeError/FileNotFoundError conforme o caso
            log.error("não consegui abrir %s: %s", args.device, exc)
            log.error("o v4l2loopback está carregado? rode scripts/setup-v4l2loopback.sh")
            return 1
    log.info("webcam virtual: %s (%dx%d @ %g fps)", sink.device, width, height, args.fps)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    options = StreamOptions(
        out_width=width,
        out_height=height,
        rotation_override=None if args.rotate == "auto" else int(args.rotate),
        mirror=args.mirror,
    )
    run(_provider(args), sink, options, stop)
    log.info("encerrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
