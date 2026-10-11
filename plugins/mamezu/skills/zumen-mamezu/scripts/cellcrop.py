"""断面の欄の中身（文字・引出し線・寸法線も含めて）を、枠線を除いて、できるだけ大きく切り出す。"""
import io
import os

import numpy as np
import pymupdf
from PIL import Image, ImageChops

TARGET_PX = 2400


def _render(page, rect, z):
    pm = page.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=rect, alpha=False)
    img = Image.open(io.BytesIO(pm.tobytes('png'))).convert('RGB')
    a = np.asarray(img).astype(int)
    mask = (a.max(axis=2) - a.min(axis=2)) > 50  # 図面に書き込まれた色付きの枠は消す
    if mask.any():
        a[mask] = 255
        img = Image.fromarray(a.astype('uint8'))
    return img


def cell_crop(doc, page_no, cell, out_path, inset=0.7, margin_ratio=0.03):
    page = doc[page_no]
    x0, y0, x1, y1 = cell
    rect = pymupdf.Rect(x0 + inset, y0 + inset, x1 - inset, y1 - inset)
    z0 = 8.0
    img = _render(page, rect, z0)
    box = ImageChops.invert(img.convert('L')).point(lambda v: 255 if v > 60 else 0).getbbox()
    if not box:
        raise ValueError(f'何も描かれていません {cell}')
    # 中身の範囲（pt）
    bx0, by0 = rect.x0 + box[0] / z0, rect.y0 + box[1] / z0
    bx1, by1 = rect.x0 + box[2] / z0, rect.y0 + box[3] / z0
    m = max(bx1 - bx0, by1 - by0) * margin_ratio
    r2 = pymupdf.Rect(bx0 - m, by0 - m, bx1 + m, by1 + m) & rect
    z = TARGET_PX / max(r2.width, r2.height)
    out = _render(page, r2, z)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.save(out_path)
    return out.size
