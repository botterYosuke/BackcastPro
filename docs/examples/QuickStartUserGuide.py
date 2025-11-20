from math import nan
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from BackcastPro import BackcastPro

# BackcastProインスタンスを作成
bp = BackcastPro()

# 株価データを取得
df = bp.set_chart('9885', '2025-01-01', '2025-01-31')

