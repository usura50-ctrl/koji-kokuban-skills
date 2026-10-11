"""図面PDFの一式から、全ての一覧表を自動で見つけ、豆図（PNG）と黒板Excelを作る（実験用）。
使い方：python run_project.py <PDF> <出力フォルダ> [工種]"""
import os
import re
import shutil
import sys
from collections import Counter

import pymupdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image

from cellcrop import cell_crop
from extract import compose, find_habadome, floor_key, natural, records, slab_compose, slab_records
from listkit import Lists, nfkc, squash

PDF = sys.argv[1]
OUT = sys.argv[2]
KOSHU = sys.argv[3] if len(sys.argv) > 3 else '鉄筋工事'
GROUPS = ['基礎梁', '柱', '梁', 'スラブ', '壁']

L = Lists(PDF)
habadome = find_habadome(L)
print('幅止め筋：', habadome)
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
report = []  # 人が確認すること


def group_of(tb):
    """表の上の題名（地中梁リスト・柱リスト…）から、まとまりを決める。"""
    pg = L.page(tb.page)
    t = squash(''.join(w for r, w in sorted(pg.words_in(tb.x0 - 5, tb.head[0] - 45, tb.x0 + 330, tb.head[0] - 1), key=lambda a: (round(a[0].y0 / 5), a[0].x0))))
    if 'スラブ' in t:
        return 'スラブ', t
    if ('地中' in t or '基礎' in t) and '梁' in t:
        return '基礎梁', t
    if '大梁' in t or '小梁' in t or '梁リスト' in t:
        return '梁', t
    if '柱' in t:
        return '柱', t
    if '壁' in t:
        return '壁', t
    return None, t


def sheet_no(pno):
    ws = L.doc[pno].get_text('words')
    cand = [nfkc(w[4]) for w in ws if re.fullmatch(r'S-\d+', nfkc(w[4]))]
    return cand[-1] if cand else f'p{pno + 1}'


items = []
page_group = {}
for pno in range(len(L.doc)):
    for tb0 in L.find_tables(pno):
        g0, _ = group_of(tb0)
        if g0 in ('基礎梁', '柱', '梁', '壁'):
            page_group.setdefault(pno, g0)
for pno in range(len(L.doc)):
    for tb in L.find_tables(pno):
        group, title = group_of(tb)
        if group is None and tb.kind != 'slab':
            # 題名の無い表（同じページの別の表）：表の種類と、同じページの表から決める
            pg_g = page_group.get(pno)
            if tb.kind == 'wall':
                group = '壁'
            elif tb.kind == 'column':
                group = '柱'
            elif tb.rows and any(rw.kind == 'size' for rw in tb.rows):
                group = pg_g if pg_g in ('基礎梁', '梁') else '梁'
        if group is None:
            if tb.kind != 'slab' or True:
                report.append(f'{sheet_no(pno)}：題名が読めない表を飛ばしました（{title[:20] or "題名なし"}）')
            continue
        if tb.kind == 'slab' or group == 'スラブ':
            try:
                recs = slab_records(L, tb)
            except ValueError:
                recs = []
            for r in recs:
                items.append(dict(group=group, name=r['sym'], naiyou=slab_compose(r), order=(0, natural(r['sym']), 0), image=None, sheet=sheet_no(pno), kind='標準', width=''))
            if not recs:
                report.append(f'{sheet_no(pno)}：スラブの表（{title[:20]}）から符号を読めませんでした')
            continue
        recs = records(L, tb)
        # 符号があるのに、値が空の列（「S-26参照」など）を知らせる
        got = {r['sym'] for r in recs}
        for a, b in tb.cols:
            sym = nfkc(squash(''.join(w for rr, w in L.page(pno).words_in(a, tb.head[0], b, tb.head[1]))))
            if sym and sym not in got:
                report.append(f'{sheet_no(pno)}：{sym} は、表に値がないので、黒板を作りませんでした（他の図を参照？）')
        for r in recs:
            name = r['sym'] + (f"_{r['floor']}階" if r['floor'] else '') + r['pos']
            items.append(dict(group=group, name=name, naiyou=compose(r, tb.kind, habadome if tb.kind in ('beam', 'wall') else None),
                              order=(floor_key(r['floor']), natural(r['sym']), r['cell'][0]), page=pno, cell=r['cell'], sheet=sheet_no(pno)))
            for n in r.get('notes', []):
                report.append(f"{sheet_no(pno)}：{name}：{n}")

# ---- 赤枠の図（一覧表でない図：要領図など）。赤枠の内側を、文字ごと切り出す
def table_box(tb):
    right = max([b for a, b in tb.cols] or [tb.x1])
    bottom = max([r.y1 for r in tb.rows] or [tb.head[1]])
    return pymupdf.Rect(tb.x0, tb.head[0], right, bottom)


def red_frames(pno):
    p = L.doc[pno]
    M = p.rotation_matrix
    out = []
    for dr in p.get_drawings():
        c = dr.get('color')
        if not c or not (c[0] > 0.7 and c[1] < 0.3 and c[2] < 0.3):
            continue
        r = dr['rect']
        r = pymupdf.Rect(r.tl * M, r.br * M).normalize()
        if r.width > 30 and r.height > 30:
            out.append(r)
    return out


for pno in range(len(L.doc)):
    frames = red_frames(pno)
    if not frames:
        continue
    pg = L.page(pno)
    tbs = [(tb, table_box(tb)) for tb in L.find_tables(pno)]
    for fr in frames:
        # 表の中の赤枠（符号・欄の目印）は、表の切り出しで足りるので飛ばす
        if any((fr & bx).get_area() > fr.get_area() * 0.3 for tb, bx in tbs):
            continue
        ws = pg.words_in(fr.x0, fr.y0, fr.x1, fr.y1)
        if not ws:
            continue
        lines = {}
        for rr, t in ws:
            lines.setdefault(round(rr.y0 / 3), []).append((rr.x0, rr.x1, t))
        texts = []
        for k, v in sorted(lines.items()):
            seg, last = '', None
            for x0, x1, t in sorted(v):
                if last is not None and x0 - last > 15:  # 同じ高さでも、離れている文字は別の注記
                    texts.append(squash(seg))
                    seg = ''
                seg += t
                last = x1
            texts.append(squash(seg))
        title = texts[0]
        name = re.sub(r'[\\/:*?"<>|]', '', title)[:30]
        # まとまり：いちばん近い表のまとまり
        best = None
        for tb, bx in tbs:
            g, _ = group_of(tb)
            if g is None:
                g = {'wall': '壁', 'column': '柱'}.get(tb.kind, page_group.get(pno))
            d = abs((bx.x0 + bx.x1) / 2 - (fr.x0 + fr.x1) / 2) + abs((bx.y0 + bx.y1) / 2 - (fr.y0 + fr.y1) / 2)
            if g in GROUPS and g != 'スラブ' and (best is None or d < best[0]):
                best = (d, g)
        group = best[1] if best else page_group.get(pno)
        if group is None:
            report.append(f'{sheet_no(pno)}：赤枠の図「{title}」の、まとまりが分かりませんでした（飛ばしました）')
            continue
        body = [t for t in texts[1:] if len(t) >= 6]
        items.append(dict(group=group, name=name, naiyou='\n'.join([title] + body), order=(1001, (name, 0, ''), fr.x0),
                          page=pno, cell=(fr.x0, fr.y0, fr.x1, fr.y1), sheet=sheet_no(pno)))
        report.append(f'{sheet_no(pno)}：赤枠の図「{name}」を、{group}のまとまりに切り出しました（黒板の文字を確認してください）')

# ---- 画像
ROW_UNIT, PAD_UNIT = 0.075, 0.18


def board_for(w, h):
    if h <= w:
        return '豆図付き', '普通'
    pad = ROW_UNIT * PAD_UNIT
    need = (8 * ROW_UNIT - 2 * pad) * (w / h) + 2 * pad
    return '豆図付き（上部拡大）', ('狭い' if need <= 0.40 else ('普通' if need <= 0.55 else '広い'))


names = Counter(i['name'] for i in items if i.get('cell'))
for n, c in names.items():
    if c > 1:
        report.append(f'同じ名前の黒板が{c}件あります（図面の間違いの可能性）：{n}')
doc = pymupdf.open(PDF)
for it in items:
    if not it.get('cell'):
        continue
    path = os.path.join(OUT, it['group'], it['name'] + '.png')
    try:
        w, h = cell_crop(doc, it['page'], it['cell'], path)
    except ValueError:
        report.append(f"{it['sheet']}：{it['name']} は、断面の欄に図がなかったので、画像を作りませんでした")
        it['image'] = None
        it['kind'], it['width'] = '標準', ''
        continue
    it['image'] = it['name'] + '.png'
    it['kind'], it['width'] = board_for(w, h)

for it in items:
    if re.search(r'：-[DKU]', it['naiyou']):
        report.append(f"{it['sheet']}：{it['name']} の値の頭に記号（□など）が付いていません。図の記号を確認してください：{it['naiyou'].splitlines()[-1] if False else [l for l in it['naiyou'].splitlines() if re.search('：-[DKU]', l)][0]}")
items.sort(key=lambda a: (GROUPS.index(a['group']), a['order']))

wb = Workbook()
sh = wb.active
sh.title = '撮影予定'
H = ['No.', '黒板の種類', '工種', '種別', '細別', '測点', '作業内容', '必要枚数', '撮影予定日', 'まとまり', '豆図ファイル', '豆図領域幅']
W = [6, 20, 14, 12, 12, 12, 40, 10, 14, 14, 26, 12]
fill = PatternFill('solid', fgColor='FFF26B0F')
thin = Side(style='thin', color='FFC9CDD3')
for i, (h, w) in enumerate(zip(H, W), 1):
    c = sh.cell(1, i, h)
    c.fill = fill
    c.font = Font(bold=True, color='FFFFFFFF')
    c.alignment = Alignment(horizontal='center', vertical='center')
    sh.column_dimensions[c.column_letter].width = w
sh.freeze_panes = 'A2'
for n, it in enumerate(items, 1):
    sh.append([n, it['kind'], KOSHU, '', '', '', it['naiyou'], 1, None, it['group'], it['image'] or '', it['width']])
    sh.row_dimensions[n + 1].height = 15 * (it['naiyou'].count('\n') + 1) + 6
for rr in range(2, max(300, len(items) + 100) + 1):
    for c in range(1, len(H) + 1):
        sh.cell(rr, c).border = Border(top=thin, bottom=thin, left=thin, right=thin)
    sh.cell(rr, 7).alignment = Alignment(wrap_text=True, vertical='top')
    sh.cell(rr, 9).number_format = 'yyyy/mm/dd'
wb.save(os.path.join(OUT, '黒板_基礎梁・柱・梁・スラブ・壁.xlsx'))

with open(os.path.join(OUT, '確認してください.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(report) if report else '確認が必要な点はありません。')
print(len(items), '行', Counter(i['group'] for i in items))
print(Counter((i['kind'], i['width']) for i in items))
print('\n'.join(report))
