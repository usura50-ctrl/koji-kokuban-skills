"""切り出した画像を、まとまり（フォルダ）ごとに、1枚の一覧画像にする。目で確認するための画像。
使い方：python contact_sheet.py <出力フォルダ> [1枚に並べる数=24]
一覧画像：<出力フォルダ>/確認/<まとまり>_<番号>.png　並びの名前は、画面に出す（左上から右へ、1から番号）。"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont


def font(size):
    for p in (r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    out = sys.argv[1]
    per = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    dest = os.path.join(out, '確認')
    os.makedirs(dest, exist_ok=True)
    f = font(22)
    for group in sorted(os.listdir(out)):
        gdir = os.path.join(out, group)
        if group == '確認' or not os.path.isdir(gdir):
            continue
        files = sorted(x for x in os.listdir(gdir) if x.lower().endswith('.png'))
        for part in range(0, len(files), per):
            chunk = files[part:part + per]
            cols = 6
            cell_w, cell_h = 330, 300
            rows = (len(chunk) + cols - 1) // cols
            sheet = Image.new('RGB', (cols * cell_w, rows * (cell_h + 34)), 'white')
            d = ImageDraw.Draw(sheet)
            for k, name in enumerate(chunk):
                im = Image.open(os.path.join(gdir, name)).convert('RGB')
                r = min((cell_w - 12) / im.width, (cell_h - 12) / im.height)
                im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
                x = (k % cols) * cell_w
                y = (k // cols) * (cell_h + 34)
                sheet.paste(im, (x + 6, y + 34))
                d.rectangle([x + 2, y + 2, x + cell_w - 3, y + cell_h + 30], outline=(190, 190, 190))
                d.text((x + 8, y + 5), f'{part + k + 1}. {os.path.splitext(name)[0]}', fill=(0, 0, 0), font=f)
            path = os.path.join(dest, f'{group}_{part // per + 1}.png')
            sheet.save(path)
            print(path)
            for k, name in enumerate(chunk):
                print(f'  {part + k + 1}. {os.path.splitext(name)[0]}')


if __name__ == '__main__':
    main()
