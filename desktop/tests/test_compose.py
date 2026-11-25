import av
import numpy as np
import pytest

from phonecam.compose import compose, fit_size


def _frame_with_marker(w=640, h=480):
    """Frame com quadrado vermelho no canto superior esquerdo."""
    img = np.full((h, w, 3), 100, dtype=np.uint8)  # fundo cinza (≠ barras pretas)
    img[: h // 4, : w // 4] = (255, 0, 0)
    return av.VideoFrame.from_ndarray(img, format="rgb24")


def _red(px):
    return px[0] > 200 and px[1] < 60 and px[2] < 60


def test_fit_size_keeps_aspect():
    assert fit_size(640, 480, 1280, 720) == (960, 720)
    assert fit_size(480, 640, 1280, 720) == (540, 720)
    assert fit_size(1920, 1080, 1280, 720) == (1280, 720)


@pytest.mark.parametrize(
    "rotation, corner",
    [
        (0, "top_left"),
        (90, "top_right"),     # girar 90° horário leva o canto sup-esq para sup-dir
        (180, "bottom_right"),
        (270, "bottom_left"),
    ],
)
def test_rotation_moves_marker(rotation, corner):
    out = compose(_frame_with_marker(), rotation, 1280, 720)
    assert out.shape == (720, 1280, 3)
    # área útil (sem as barras pretas)
    cols = np.where(out.any(axis=(0, 2)))[0]
    rows = np.where(out.any(axis=(1, 2)))[0]
    top, bottom, left, right = rows[0], rows[-1], cols[0], cols[-1]
    probes = {
        "top_left": out[top + 5, left + 5],
        "top_right": out[top + 5, right - 5],
        "bottom_right": out[bottom - 5, right - 5],
        "bottom_left": out[bottom - 5, left + 5],
    }
    assert _red(probes[corner])
    for name, px in probes.items():
        if name != corner:
            assert not _red(px), name


def test_portrait_is_pillarboxed():
    out = compose(_frame_with_marker(), 90, 1280, 720)
    # 640x480 girado vira 480x640 -> cabe como 540x720 centralizado
    assert not out[:, :300].any()
    assert not out[:, -300:].any()


def test_mirror():
    out = compose(_frame_with_marker(1280, 720), 0, 1280, 720, mirror=True)
    assert _red(out[5, -5]) and not _red(out[5, 5])
