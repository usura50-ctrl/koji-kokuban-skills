"""一覧表（符号ごとの配筋リスト）を、ページごとの座標を決め打ちせずに、罫線と文字から読み取る。
- 「符号」の欄を見つけ、その表の行（項目名）・列（符号）・階のまとまりを、罫線から割り出す。
- 項目名（位置・断面・b x D・上端筋・…）で、値の意味を決める。図面ごとの違いは、項目名の言葉の違いだけで吸収する。"""
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np

from cropkit import Page


def nfkc(s):
    return unicodedata.normalize('NFKC', s)


def squash(s):
    return re.sub(r'\s+', '', nfkc(s))


def norm_value(s):
    """値の文字：全角→半角、記号をそろえる（例：2-D13-＠150 → 2-D13@150）。"""
    s = nfkc(s)
    s = re.sub(r'\s+', '', s)
    s = s.replace('－', '-').replace('ー', '-')
    s = re.sub(r'-@', '@', s)
    s = s.replace('φ', 'φ')
    s = re.sub(r'(D\d+)(D\d+)', r'\1・\2', s)
    return s


# 行の項目名（正規化後）の、意味
ROW_KINDS = [
    ('pos', r'^位置'),
    ('section', r'断面'),
    ('floor', r'^([0-9０-９]+|[RＲ]|PH|ＰＨ|地下[0-9]*)階'),
    ('size', r'^(b[xX×]D|Dx[xX×]Dy|寸法)'),
    ('level', r'^.{0,6}SL$'),
    ('joint', r'仕口'),
    ('note', r'^備考'),
]
VOCAB = re.compile(r'(位置|断面|階|b[xX×]D|Dx[xX×]Dy|上端筋|下端筋|スターラップ|STP|あばら筋|腹筋|主筋|フープ|HOOP|縦筋|横筋|開口|補強筋|備考|縦|横|斜メ|斜め|仕口|▽|SL|^[RＲ]$|^[0-9]+$)')


def row_kind(label):
    for k, pat in ROW_KINDS:
        if re.search(pat, label):
            return k
    return 'data'


@dataclass
class Row:
    y0: float
    y1: float
    label: str
    kind: str
    tall: bool


@dataclass
class Table:
    page: int
    x0: float  # 表の左端（項目名の欄の左）
    x1: float  # 項目名の欄の右端
    head: tuple  # 見出し行（符号）の (y0, y1)
    rows: list
    cols: list  # 見出し行の列の区切り（符号のセル）[(x0, x1)]
    kind: str = 'beam'


class Lists:
    def __init__(self, pdf_path):
        self.pdf = pdf_path
        import pymupdf
        self.doc = pymupdf.open(pdf_path)
        self.pages = {}

    def page(self, i):
        if i not in self.pages:
            self.pages[i] = Page(self.pdf, i)
        return self.pages[i]

    # ---- 表を見つける
    def find_tables(self, i):
        pg = self.page(i)
        out = []
        for r, t in pg.words:
            if squash(t) != '符号':
                continue
            tb = self._parse(pg, i, r)
            if tb:
                out.append(tb)
        return out

    def _cell_around(self, pg, r):
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        ys = sorted(set(y for y, a, b in pg.H if a <= cx <= b))
        top = max([y for y in ys if y <= cy - 2] or [None], key=lambda v: -1e9 if v is None else v)
        bot = min([y for y in ys if y >= cy + 2] or [None], key=lambda v: 1e9 if v is None else v)
        if top is None or bot is None:
            return None
        xs = sorted(set(x for x, a, b in pg.V if a <= top + 1.5 and b >= bot - 1.5))
        left = max([x for x in xs if x <= r.x0 + 1] or [None], key=lambda v: -1e9 if v is None else v)
        right = min([x for x in xs if x >= r.x1 - 1] or [None], key=lambda v: 1e9 if v is None else v)
        if left is None or right is None:
            return None
        return left, top, right, bot

    def _parse(self, pg, i, word):
        cell = self._cell_around(pg, word)
        if not cell:
            return None
        left, top, right, bot = cell
        w = right - left
        # 見出しの下の行：項目名の欄の右側を貫く横線
        need = lambda y, a, b: a <= right - w * 0.25 + 1 and b >= right - 1
        cand = [(y, a) for y, a, b in pg.H if y > bot - 0.5 and need(y, a, b)]
        lines = sorted(set(y for y, a in cand))
        # 同じ高さの線は1本に（線の左端＝その線が、項目名の欄のどこから始まるか）
        start_of = {}
        for y, a in cand:
            start_of[y] = min(start_of.get(y, 1e9), a)
        ys = [bot]
        for y in lines:
            if y - ys[-1] > 0.8:
                ys.append(y)
        start_of.setdefault(bot, left)
        rows = []
        for a, b in zip(ys[:-1], ys[1:]):
            # 項目名の欄が2段（開口部補強筋の 縦・横・斜メ など）の行は、右の段の文字を項目名にする
            lx = max(start_of.get(a, left), start_of.get(b, left))
            lx = lx if lx > left + 10 else left
            label = squash(''.join(t for rr, t in pg.words_in(lx, a, right, b)))
            tall = (b - a) >= 40
            kind = row_kind(label)
            if not tall and kind == 'data' and not VOCAB.search(label):
                break  # 項目名として読めない行＝表の終わり（スラブの表・次の表）
            if not tall and not label:
                break
            if tall and kind not in ('section', 'floor', 'level'):
                break  # 背の高い行は、断面・階の行だけ（特記事項などは表の外）
            rows.append(Row(a, b, label, kind, tall))
        if not rows:
            return Table(i, left, right, (top, bot), [], self._head_cols(pg, right, top, bot, left), 'slab')
        cols = self._head_cols(pg, right, top, bot, left)
        kinds = [r.label for r in rows]
        joined = ' '.join(kinds)
        if '立断面' in joined:
            kind = 'wall'
        elif re.search(r'Dx[xX×]Dy', joined):
            kind = 'column'
        elif any(r.kind == 'pos' for r in rows):
            kind = 'beam'
        else:
            kind = 'beam'
        return Table(i, left, right, (top, bot), rows, cols, kind)

    def _head_cols(self, pg, right, top, bot, left=None):
        # 表の右端：見出しの上の線（左端から続く線）の右端
        edge = max([b for y, a, b in pg.H if abs(y - top) < 0.8 and left is not None and a <= left + 1.5] or [1e9])
        xs = sorted(set(x for x, a, b in pg.V if a <= top + 1.5 and b >= bot - 1.5 and right - 0.5 <= x <= edge + 0.5))
        return list(zip(xs[:-1], xs[1:]))

    # ---- 値
    def cell_text(self, pg, x0, x1, y0, y1):
        ws = pg.words_in(x0, y0, x1, y1)
        return norm_value(''.join(t for r, t in ws))
