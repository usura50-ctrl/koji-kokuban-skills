"""図面PDF（CAD出力）の表を、符号ごとに切り出すための部品。罫線の位置から切り出す（日本語の文字は読み取らない）。"""
import io
import os

import numpy as np
import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFont

Z = 8.0
def _load_font():
    for p in (r"C:\Windows\Fonts\msgothic.ttc", r"C:\Windows\Fonts\meiryo.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        try:
            return ImageFont.truetype(p, int(7.2 * Z))
        except OSError:
            continue
    return ImageFont.load_default()


FONT = _load_font()
PAD = 0.3


class Page:
    def __init__(self, pdf_path, pno):
        self.doc = pymupdf.open(pdf_path)
        self.p = self.doc[pno]
        M = self.p.rotation_matrix
        self.H, self.V, self.D = [], [], []
        for dr in self.p.get_drawings():
            for it in dr['items']:
                if it[0] != 'l':
                    continue
                a, b = it[1] * M, it[2] * M
                if abs(a.y - b.y) < 0.3:
                    self.H.append((round(a.y, 1), round(min(a.x, b.x), 1), round(max(a.x, b.x), 1)))
                elif abs(a.x - b.x) < 0.3:
                    self.V.append((round(a.x, 1), round(min(a.y, b.y), 1), round(max(a.y, b.y), 1)))
                else:
                    self.D.append((a.x, a.y, b.x, b.y))
        self.H = sorted(set(self.H))
        self.V = sorted(set(self.V))
        self.words = []
        for w in self.p.get_text('words'):
            r = pymupdf.Rect(w[:4])
            self.words.append((pymupdf.Rect(r.tl * M, r.br * M).normalize(), w[4]))

    # ---- 罫線
    def dividers(self, y0, y1):
        """行 [y0,y1] を縦に貫いている縦線の x（昇順）。"""
        return sorted(set(x for x, a, b in self.V if a <= y0 + 0.8 and b >= y1 - 0.8))

    def hlines(self, x0, x1, ymin, ymax, minlen=20):
        """x0〜x1 を横切る横線の y（昇順・重複除く）。"""
        ys = sorted(set(y for y, a, b in self.H if ymin - 0.3 <= y <= ymax + 0.3 and a <= x0 + 1 and b >= x1 - 1 and b - a >= minlen))
        out = []
        for y in ys:
            if not out or y - out[-1] > 0.6:
                out.append(y)
        return out

    def has_diagonal(self, x0, y0, x1, y1):
        """セルの対角線（斜線）があるか。"""
        for ax, ay, bx, by in self.D:
            if abs(ax - bx) < 8 or abs(ay - by) < 8:
                continue
            xs = (min(ax, bx), max(ax, bx))
            ys = (min(ay, by), max(ay, by))
            if xs[0] >= x0 - 3 and xs[1] <= x1 + 3 and ys[0] >= y0 - 20 and ys[1] <= y1 + 20 and (xs[1] - xs[0]) > (x1 - x0) * 0.6 and (ys[1] - ys[0]) > (y1 - y0) * 0.6:
                return True
        return False

    def words_in(self, x0, y0, x1, y1):
        out = []
        for r, t in self.words:
            cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                out.append((r, t))
        return sorted(out, key=lambda a: (round(a[0].y0 / 3), a[0].x0))

    # ---- 画像
    def px(self, x0, y0, x1, y1):
        pm = self.p.get_pixmap(matrix=pymupdf.Matrix(Z, Z), clip=pymupdf.Rect(x0, y0, x1, y1), alpha=False)
        img = Image.open(io.BytesIO(pm.tobytes('png'))).convert('RGB')
        # 図面に書き込まれた色付きの枠（赤・緑・黄の目印）は、切り出しに入れない
        a = np.asarray(img).astype(int)
        mask = (a.max(axis=2) - a.min(axis=2)) > 50
        if mask.any():
            a[mask] = 255
            img = Image.fromarray(a.astype('uint8'))
        return img


def content_bbox(img, thr=90):
    return ImageChops.invert(img.convert('L')).point(lambda v: 255 if v > thr else 0).getbbox()


def is_blank(page, x0, y0, x1, y1, inset=0.6):
    return content_bbox(page.px(x0 + inset, y0 + inset, x1 - inset, y1 - inset)) is None


def merged_range(page, ya, yb, cx0, cx1):
    """行 [ya,yb] で、列 [cx0,cx1] が含まれているセルの左右の端（結合セルなら列より広い）。"""
    divs = page.dividers(ya, yb)
    left = max([x for x in divs if x <= cx0 + 0.8] or [cx0])
    right = min([x for x in divs if x >= cx1 - 0.8] or [cx1])
    return left, right


def center_patch(page, img, img_x0_pt, img_y0_pt, ya, yb, mr, col):
    """結合セル（mr）の中身を、列（col）のセルの中央に書き入れる。img は列の画像（左上が img_x0_pt, img_y0_pt）。"""
    full = page.px(mr[0] + 0.5, ya + 0.5, mr[1] - 0.5, yb - 0.5)
    bb = content_bbox(full)
    if not bb:
        return False
    patch = full.crop(bb)
    d = ImageDraw.Draw(img)
    tx0 = 0
    tx1 = img.width
    ty0 = int((ya + 0.5 - img_y0_pt) * Z)
    ty1 = int((yb - 0.5 - img_y0_pt) * Z)
    d.rectangle([tx0, ty0, tx1, ty1], fill='white')
    cx = int(((col[0] + col[1]) / 2 - img_x0_pt) * Z)
    img.paste(patch, (cx - patch.width // 2, ty0 + (ty1 - ty0 - patch.height) // 2))
    return True


def draw_center(img, text, x0, x1, y0, y1, font=FONT):
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), text, font=font)
    d.text((x0 + (x1 - x0 - (bb[2] - bb[0])) / 2 - bb[0], y0 + (y1 - y0 - (bb[3] - bb[1])) / 2 - bb[1]), text, fill='black', font=font)


def hstack(a, b):
    out = Image.new('RGB', (a.width + b.width, max(a.height, b.height)), 'white')
    out.paste(a, (0, 0))
    out.paste(b, (a.width, 0))
    return out


def vstack(*imgs):
    out = Image.new('RGB', (max(i.width for i in imgs), sum(i.height for i in imgs)), 'white')
    y = 0
    for i in imgs:
        out.paste(i, (0, y))
        y += i.height
    return out


def seam_lines(img, ys_px, thick=False):
    d = ImageDraw.Draw(img)
    for y in ys_px:
        d.line([(0, y), (img.width, y)], fill='black', width=4 if thick else 2)


def finish_edges(img, seam_x):
    """左右の縁の線をそろえる（左右の境目は太く、右端は細く）。"""
    d = ImageDraw.Draw(img)
    d.line([(seam_x, 0), (seam_x, img.height)], fill='black', width=4)
    rx = img.width - int(PAD * Z)
    d.rectangle([rx - 2, 0, img.width, img.height], fill='white')
    d.line([(rx, 0), (rx, img.height)], fill='black', width=3)
    d.line([(int(PAD * Z), 0), (int(PAD * Z), img.height)], fill='black', width=4)
    return img


SAVE_ENABLED = True


def save(img, folder, name):
    if not SAVE_ENABLED:
        return None
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + '.png')
    img.save(path, dpi=(Z * 72, Z * 72))
    return path
