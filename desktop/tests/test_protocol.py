import io

import pytest

from phonecam.protocol import (
    Config, Frame, ProtocolError, encode_config, encode_frame, encode_handshake,
    read_handshake, read_packet,
)


def test_roundtrip():
    cfg = Config(1280, 720, 90, 1, b"\x00\x00\x00\x01gSPS\x00\x00\x00\x01hPPS")
    fr = Frame(True, 123_456_789, b"\x00\x00\x00\x01e" + b"x" * 1000)
    stream = io.BytesIO(encode_handshake() + encode_config(cfg) + encode_frame(fr))

    assert read_handshake(stream) == 1
    assert read_packet(stream) == cfg
    assert read_packet(stream) == fr
    with pytest.raises(EOFError):
        read_packet(stream)


def test_bad_magic():
    with pytest.raises(ProtocolError):
        read_handshake(io.BytesIO(b"HTTP/1.1"))


def test_unknown_type_is_skipped():
    unknown = bytes([99]) + (3).to_bytes(4, "big") + b"abc"
    fr = Frame(False, 1, b"zz")
    stream = io.BytesIO(unknown + encode_frame(fr))
    assert read_packet(stream) is None
    assert read_packet(stream) == fr


def test_truncated_payload():
    data = encode_frame(Frame(False, 1, b"abcdef"))[:-2]
    with pytest.raises(EOFError):
        read_packet(io.BytesIO(data))


def test_huge_length_rejected():
    with pytest.raises(ProtocolError):
        read_packet(io.BytesIO(bytes([2]) + (1 << 30).to_bytes(4, "big")))
