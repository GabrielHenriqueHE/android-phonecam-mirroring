"""Decodificação H.264 com PyAV (FFmpeg)."""

from __future__ import annotations

import logging

import av
from av.codec.context import Flags

log = logging.getLogger(__name__)


class H264Decoder:
    """Recebe access units Annex-B completos e devolve frames decodificados.

    Não usa o parser do FFmpeg de propósito: o celular já manda um access unit por
    pacote, e o parser seguraria cada frame até o próximo start code chegar
    (1 frame a mais de latência).
    """

    def __init__(self) -> None:
        self._codec_config = b""
        self._ctx: av.VideoCodecContext | None = None
        self._waiting_keyframe = True
        self.reset()

    def reset(self) -> None:
        ctx = av.CodecContext.create("h264", "r")
        ctx.flags |= Flags.low_delay
        self._ctx = ctx
        self._waiting_keyframe = True

    def set_codec_config(self, codec_config: bytes) -> None:
        if codec_config != self._codec_config:
            self._codec_config = codec_config
            self.reset()

    def decode(self, data: bytes, keyframe: bool) -> list[av.VideoFrame]:
        if self._waiting_keyframe:
            if not keyframe:
                return []
            self._waiting_keyframe = False

        # Muitos encoders Android só mandam SPS/PPS no buffer de config; repetir antes
        # de cada keyframe deixa o decoder se recuperar sozinho.
        if keyframe and self._codec_config:
            data = self._codec_config + data

        try:
            return list(self._ctx.decode(av.Packet(data)))
        except av.error.FFmpegError as exc:
            log.warning("erro de decodificação (%s); aguardando próximo keyframe", exc)
            self._waiting_keyframe = True
            return []
