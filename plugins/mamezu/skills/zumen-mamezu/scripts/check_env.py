"""必要なPythonの部品が入っているか確認し、足りなければ pip で入れる。"""
import importlib
import os
import subprocess
import sys

NEEDED = {'pymupdf': 'PyMuPDF', 'PIL': 'Pillow', 'openpyxl': 'openpyxl', 'numpy': 'numpy'}
missing = []
for mod, pkg in NEEDED.items():
    try:
        importlib.import_module(mod)
    except ImportError:
        missing.append(pkg)
if missing:
    print('足りない部品を入れます：', ', '.join(missing))
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', *missing])
    print('入れました。')
else:
    print('必要な部品は、そろっています。')
print('Python', sys.version.split()[0], os.path.basename(sys.executable))
