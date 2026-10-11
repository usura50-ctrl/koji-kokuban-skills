"""一覧表（listkit が見つけた表）から、符号・階・位置ごとの記録を取り出し、黒板の文字を作る。"""
import re

from cropkit import content_bbox, merged_range
from listkit import Lists, Row, Table, nfkc, norm_value, squash

JOINT = '仕口'


def floor_of(label):
    m = re.match(r'^([0-9０-９]+|[RＲ]|PH|ＰＨ)階', nfkc(label).replace(' ', ''))
    return nfkc(m.group(1)) if m else ''


def floor_key(fl):
    if fl == '':
        return 1000  # 階の無いもの（小梁など）は、階のあるものの後ろ
    if fl in ('R', 'PH'):
        return 99
    return int(fl)


def natural(sym):
    m = re.match(r'^([A-Za-z]+)(\d+)(.*)$', sym)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (sym, 0, '')


def blocks_of(tb: Table):
    """断面（背の高い行）から始まるまとまり：[(背の高い行, [データの行])]。"""
    out = []
    cur = None
    for r in tb.rows:
        if r.tall and r.kind in ('section', 'floor'):
            cur = (r, [])
            out.append(cur)
        elif r.kind in ('joint',):
            cur = None  # 仕口部の行は、その階のものではない（その階だけを切り出す方針）
        elif r.kind == 'level':
            continue
        elif cur is not None and r.kind in ('data', 'size'):
            cur[1].append(r)
    return out


def positions_of(L: Lists, tb: Table):
    """位置の列（位置の行の区切り）。位置の行が無い表は、見出しの列がそのまま。"""
    pg = L.page(tb.page)
    pos_rows = [r for r in tb.rows if r.kind == 'pos']
    right = tb.cols[-1][1] if tb.cols else 1e9
    if pos_rows:
        r = pos_rows[0]
        divs = [x for x in pg.dividers(r.y0 + 0.8, r.y1 - 0.8) if tb.x1 - 0.5 <= x <= right + 0.5]
        cols = list(zip(divs[:-1], divs[1:]))
        names = [squash(''.join(t for rr, t in pg.words_in(a, r.y0, b, r.y1))) for a, b in cols]
        return list(zip(cols, names))
    return [(c, '') for c in tb.cols]


def symbol_of(L, tb, col):
    pg = L.page(tb.page)
    cx = (col[0] + col[1]) / 2
    for a, b in tb.cols:
        if a - 0.5 <= cx <= b + 0.5:
            return squash(''.join(t for rr, t in pg.words_in(a, tb.head[0], b, tb.head[1])))
    return ''


def records(L: Lists, tb: Table):
    pg = L.page(tb.page)
    out = []
    pos_cols = positions_of(L, tb)
    for tall, data in blocks_of(tb):
        fl = floor_of(tall.label)
        y_top = tall.y0
        y_bot = data[-1].y1 if data else tall.y1
        for col, pname in pos_cols:
            if pname == '' and tb.rows and any(r.kind == 'pos' for r in tb.rows):
                continue
            sym = symbol_of(L, tb, col)
            if not sym:
                continue
            if any(r.kind == 'pos' for r in tb.rows) and not pname:
                continue  # 位置が空の列（斜線の欄）
            hc = next(((a, b) for a, b in tb.cols if a - 0.5 <= (col[0] + col[1]) / 2 <= b + 0.5), col)
            if pg.has_diagonal(hc[0], y_top, hc[1], y_bot) or pg.has_diagonal(col[0], y_top, col[1], y_bot):
                continue  # 斜線の欄（その符号・階は無い）
            vals = []
            for r in data:
                mr = merged_range(pg, r.y0, r.y1, col[0], col[1])
                txt = norm_value(''.join(t for rr, t in pg.words_in(mr[0], r.y0, mr[1], r.y1)))
                if re.search(r'フープ|HOOP', r.label):
                    txt = re.sub(r'(\)|^)(-D\d+|-K\d+|-U[0-9.]+)', r'\1□\2', txt)  # 帯筋の記号（□）は図なので、文字に補う
                txt = re.sub(r'(@\d+)([SDC])$', r'\1 \2', txt)  # 壁：D10@200 D（S：シングル・D：ダブル・C：チドリ）
                if not txt and content_bbox(pg.px(mr[0] + 0.6, r.y0 + 0.6, mr[1] - 0.6, r.y1 - 0.6)) is not None:
                    txt = '—'
                vals.append((r, txt))
            if not any(v for r, v in vals):
                continue
            wall_text = ''.join(t for rr, t in pg.words_in(col[0], tall.y0, col[1], tall.y1))
            out.append(dict(table=tb, sym=nfkc(sym), floor=fl, pos=nfkc(pname), vals=vals, cell=(col[0], tall.y0, col[1], tall.y1), page=tb.page,
                            tall_words=[t for rr, t in pg.words_in(col[0], tall.y0, col[1], tall.y1)]))
    return out


def head_line(rec):
    sym, fl, pos = rec['sym'], rec['floor'], rec['pos']
    size = ''
    for r, v in rec['vals']:
        if r.kind == 'size':
            size = re.sub(r'x', '×', v)
    parts = [f'{sym}：' + (f'{fl}階　' if fl else '') + (f'{pos}　' if pos else '')]
    return ''.join(parts) + size


def label_of(r):
    return r.label


def compose(rec, kind, habadome):
    """黒板の作業内容。項目名は、図面の項目名のまま。"""
    lines = [head_line(rec)]
    wall_open = []
    for r, v in rec['vals']:
        if r.kind == 'size' or not v:
            continue
        lab = r.label
        if kind == 'wall' and lab in ('縦', '横', '斜メ', '斜め'):
            wall_open.append(f'{lab}{v}')
            continue
        lines.append(f'{lab}：{v}')
    if wall_open:
        lines.append('開口部補強筋：' + '　'.join(wall_open))
    if kind in ('beam', 'wall') and habadome:
        lines.insert(len(lines), f'幅止め筋：{habadome}')
    if kind == 'wall':
        th = [t for t in rec['tall_words'] if re.fullmatch(r'\d{3}', nfkc(t))]
        if th:
            lines[0] = f"{rec['sym']}：壁厚{nfkc(th[-1])}"
    return '\n'.join(lines)


def find_habadome(L: Lists, hint_pages=None):
    """特記事項の「巾止筋はD10-@1000以内」から、幅止め筋の値を探す。"""
    for i in range(len(L.doc)):
        t = nfkc(L.doc[i].get_text())
        m = re.search(r'[巾幅]止め?筋[^D]{0,12}(D\d+)[^0-9@]{0,4}@\s*([0-9 ]{3,6})', t)
        if m:
            return f"{m.group(1)}@{re.sub(r' ', '', m.group(2))}"
    return None


# ---------- スラブリスト（文字だけ。豆図なし） ----------
SYM_RE = re.compile(r'^[A-Z]{1,3}\d+[A-Z]*$')


def slab_records(L: Lists, tb: Table):
    pg = L.page(tb.page)
    left, (top, bot) = tb.x0, tb.head
    right_edge = max([b for y, a, b in pg.H if abs(y - top) < 0.8 and a <= left + 1.5] or [1e9])
    # 符号の欄（左端の欄）に並ぶ符号
    # 表の下の端：表の全幅の横線の、いちばん下（その下の図の文字を、符号と間違えない）
    wide = [y for y, a, b in pg.H if y > top and a <= left + 1.5 and b >= left + (right_edge - left) * 0.95 and b <= right_edge + 3 and y < top + 700]
    table_bottom = max(wide) if wide else 1e9
    syms = []
    for r, t in pg.words:
        tt = nfkc(t)
        if left - 1 <= r.x0 and r.x1 <= tb.x1 + 1 and r.y0 > bot - 2 and r.y1 <= table_bottom + 1 and SYM_RE.match(tt):
            syms.append((r.y0, r.y1, tt))
    syms.sort()
    if not syms:
        return []
    # 符号の続きの範囲だけ（表の下の別の図の文字を拾わない）
    ys = [s[0] for s in syms]
    keep = [syms[0]]
    for s in syms[1:]:
        if s[0] - keep[-1][0] <= 120:
            keep.append(s)
        else:
            break
    syms = keep
    ymid = (syms[0][0] + syms[0][1]) / 2
    divs = sorted(set(x for x, a, b in pg.V if a <= ymid + 1 and b >= ymid - 1 and left - 0.5 <= x <= right_edge + 0.5))
    cols = list(zip(divs[:-1], divs[1:]))
    # 見出し（表の上から、最初の符号の少し上まで）
    first_pos = min([rr.y0 for rr, t in pg.words if '端筋' in squash(t) and left <= rr.x0 <= right_edge and rr.y0 > bot] or [syms[0][0]])
    hdr_bottom = min(syms[0][0], first_pos) - 2
    heads = []
    for a, b in cols:
        txt = squash(''.join(t for rr, t in sorted(pg.words_in(a, top, b, hdr_bottom), key=lambda w: (round(w[0].y0 / 4), w[0].x0))))
        heads.append(txt)
    roles = []
    for h in heads:
        if h.startswith('符号'):
            roles.append('sym')
        elif re.search(r'版厚|^t|元端|先端', h):
            roles.append('thick')
        elif '位置' in h:
            roles.append('pos')
        elif '備考' in h:
            roles.append('note')
        else:
            roles.append('val')
    out = []
    for k, (y0, y1, sym) in enumerate(syms):
        end = syms[k + 1][0] - 4 if k + 1 < len(syms) else y0 + 60
        start = y0 - 8
        # 位置（上端筋・下端筋）の行
        pi = roles.index('pos')
        prow = [(rr.y0, rr.y1, squash(t)) for rr, t in pg.words_in(cols[pi][0], start, cols[pi][1], end) if '端筋' in squash(t)]
        prow.sort()
        rec = dict(sym=sym, page=tb.page, thick=[], vals=[], note='', table=tb)
        for (a, b), role, h in zip(cols, roles, heads):
            if role == 'thick':
                v = ''.join(t for rr, t in pg.words_in(a, start, b, end))
                rec['thick'].append((h, norm_value(v)))
            elif role == 'val':
                items = []
                for y_a, y_b, pname in prow:
                    yc = (y_a + y_b) / 2
                    v = ''.join(t for rr, t in sorted(pg.words_in(a, yc - 5.5, b, yc + 5.5), key=lambda w: w[0].x0))
                    items.append((pname, norm_value(v)))
                rec['vals'].append((h, items))
            elif role == 'note':
                rec['note'] = norm_value(''.join(t for rr, t in pg.words_in(a, start, b, end)))
        out.append(rec)
    return out


def slab_compose(rec):
    th = [(h, v) for h, v in rec['thick'] if v]
    if len(th) >= 2:
        t = '　'.join(f"{re.sub('版厚', '', h) or '版厚'}{v}" for h, v in th)
        head = f"{rec['sym']}　版厚 {t}"
    elif th:
        head = f"{rec['sym']}　版厚{th[0][1]}"
    else:
        head = rec['sym']
    lines = [head]
    for h, items in rec['vals']:
        lines.append(f"{h}：" + '　'.join(f'{p} {v}' for p, v in items))
    if rec['note']:
        lines.append(f"備考：{rec['note']}")
    return '\n'.join(lines)
