"""Wire protocol between the Android app (server) and the desktop client.

Everything is big-endian. Spec in ../../docs/PROTOCOL.md.

    handshake : b"PCAM" + u8 version
    packet    : u8 type + u32 payload_len + payload

    CONFIG (1): u16 width, u16 height, u16 rotation, u8 facing, bytes codec_config (SPS/PPS, Annex-B)
    FRAME  (2): u8 flags (bit0 = keyframe), i64 pts_us, bytes access_unit (Annex-B)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO

MAGIC = b"PCAM"
VERSION = 1

TYPE_CONFIG = 1
TYPE_FRAME = 2

FACING_BACK = 0
FACING_FRONT = 1

FLAG_KEYFRAME = 0x01

MAX_PAYLOAD = 16 * 1024 * 1024  # guarda contra lixo na rede

_HEADER = struct.Struct(">BI")
_CONFIG_HEAD = struct.Struct(">HHHB")
_FRAME_HEAD = struct.Struct(">Bq")


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    width: int
    height: int
    rotation: int
    facing: int
    codec_config: bytes


@dataclass(frozen=True)
class Frame:
    keyframe: bool
    pts_us: int
    data: bytes


Packet = Config | Frame


def _read_exact(stream: BinaryIO, n: int) -> bytes:
    buf = stream.read(n)
    if buf is None or len(buf) != n:
        raise EOFError("conexão encerrada pelo celular")
    return buf


def read_handshake(stream: BinaryIO) -> int:
    head = _read_exact(stream, len(MAGIC) + 1)
    if head[:4] != MAGIC:
        raise ProtocolError(f"magic inválido: {head[:4]!r}")
    version = head[4]
    if version != VERSION:
        raise ProtocolError(f"versão de protocolo {version} não suportada (esperado {VERSION})")
    return version


def read_packet(stream: BinaryIO) -> Packet | None:
    """Lê um pacote. Retorna None para tipos desconhecidos (compatibilidade futura)."""
    ptype, length = _HEADER.unpack(_read_exact(stream, _HEADER.size))
    if length > MAX_PAYLOAD:
        raise ProtocolError(f"payload grande demais: {length} bytes")
    payload = _read_exact(stream, length)

    if ptype == TYPE_CONFIG:
        if length < _CONFIG_HEAD.size:
            raise ProtocolError("CONFIG truncado")
        w, h, rot, facing = _CONFIG_HEAD.unpack_from(payload)
        if rot not in (0, 90, 180, 270):
            raise ProtocolError(f"rotação inválida: {rot}")
        return Config(w, h, rot, facing, payload[_CONFIG_HEAD.size:])

    if ptype == TYPE_FRAME:
        if length < _FRAME_HEAD.size:
            raise ProtocolError("FRAME truncado")
        flags, pts = _FRAME_HEAD.unpack_from(payload)
        return Frame(bool(flags & FLAG_KEYFRAME), pts, payload[_FRAME_HEAD.size:])

    return None


# --- encoders (usados nos testes e no celular falso) ---------------------------------

def encode_handshake() -> bytes:
    return MAGIC + bytes([VERSION])


def encode_config(cfg: Config) -> bytes:
    payload = _CONFIG_HEAD.pack(cfg.width, cfg.height, cfg.rotation, cfg.facing) + cfg.codec_config
    return _HEADER.pack(TYPE_CONFIG, len(payload)) + payload


def encode_frame(frame: Frame) -> bytes:
    payload = _FRAME_HEAD.pack(FLAG_KEYFRAME if frame.keyframe else 0, frame.pts_us) + frame.data
    return _HEADER.pack(TYPE_FRAME, len(payload)) + payload
