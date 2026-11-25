"""Converte um frame decodificado para o tamanho fixo da webcam virtual.

A webcam virtual tem tamanho FIXO: se o formato do /dev/videoN mudar enquanto o
Chrome está lendo, o Meet perde o vídeo. Então rotação, troca de câmera e
reconexão viram só letterbox dentro do mesmo canvas.
"""

from __future__ import annotations

import av
import numpy as np

PLACEHOLDER_RGB = (32, 32, 36)


def _even(x: float) -> int:
    return max(2, int(x) // 2 * 2)


def fit_size(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[int, int]:
    """Maior tamanho (par) que cabe em out_w x out_h mantendo a proporção."""
    scale = min(out_w / src_w, out_h / src_h)
    return min(out_w, _even(src_w * scale)), min(out_h, _even(src_h * scale))


def compose(
    frame: av.VideoFrame,
    rotation: int,
    out_w: int,
    out_h: int,
    mirror: bool = False,
) -> np.ndarray:
    """Retorna array RGB (out_h, out_w, 3) com o frame rotacionado e centralizado.

    `rotation` segue a convenção do CameraX: graus no sentido HORÁRIO para deixar a
    imagem em pé.
    """
    quarter = (rotation // 90) % 4
    upright_w, upright_h = (frame.height, frame.width) if quarter % 2 else (frame.width, frame.height)
    fit_w, fit_h = fit_size(upright_w, upright_h, out_w, out_h)

    # escala ANTES de rotacionar (rotacionar uma imagem menor é mais barato)
    pre_w, pre_h = (fit_h, fit_w) if quarter % 2 else (fit_w, fit_h)
    img = frame.reformat(width=pre_w, height=pre_h, format="rgb24").to_ndarray()

    if quarter:
        img = np.rot90(img, k=(4 - quarter) % 4)  # rot90 gira anti-horário
    if mirror:
        img = img[:, ::-1]

    if fit_w == out_w and fit_h == out_h:
        return np.ascontiguousarray(img)

    canvas = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    y0 = (out_h - fit_h) // 2
    x0 = (out_w - fit_w) // 2
    canvas[y0:y0 + fit_h, x0:x0 + fit_w] = img
    return canvas


def placeholder(out_w: int, out_h: int) -> np.ndarray:
    img = np.empty((out_h, out_w, 3), dtype=np.uint8)
    img[:] = PLACEHOLDER_RGB
    return img
