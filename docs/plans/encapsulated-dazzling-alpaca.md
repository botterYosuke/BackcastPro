# update-stocks-price 高速化計画

## 現状のボトルネック

~3,800銘柄を **完全逐次処理** しており、1銘柄あたり:
1. Tachibana API → 2. Stooq API → 3. J-Quants API → 4. DuckDB保存
これを3,800回繰り返した後、FTPアップロードも1ファイルずつ個別接続。

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `tasks/update_stocks_price.py` | フェーズ別並列化 + FTPバッチアップロード |

## スレッドセーフ性の分析

| コンポーネント | スレッドセーフ | 理由 |
|--------------|:---:|------|
| DuckDB保存 | ✅ | 銘柄別に独立した `.duckdb` ファイル、接続は都度生成 |
| `stocks_price()` 生成 | ✅ | 軽量（パス設定のみ）、スレッド別インスタンスで安全 |
| Stooq API | ✅ | ステートレスな HTTP GET |
| J-Quants API | ⚠️ | シングルトン。スレッドセーフだが **レート制限あり** |
| Tachibana e-API | ❌ | シングルトンで `p_no` カウンタ・セッション状態を共有。並列アクセスで不整合 |

## 変更内容

### 1. フェーズ別並列化（銘柄単位ではなく処理フェーズ単位）

銘柄単位の並列化は Tachibana の共有状態問題を抱えるため、**API ごとにフェーズ分割**し、各 API の特性に合った並列度で処理する。

```
Phase 1: Tachibana 全銘柄取得（直列 — p_no/セッション状態の共有問題）
Phase 2: Stooq 全銘柄取得（8並列 — ステートレス）
Phase 3: J-Quants 全銘柄取得（4並列 + レート制限 — API制約）
Phase 4: マージ + DuckDB保存（8並列 — 銘柄別ファイルなので安全）
Phase 5: FTP バッチアップロード（単一接続）
```

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Phase 1: Tachibana（直列） ---
tachibana_results = {}  # code -> DataFrame
sp = stocks_price()
for code in codes:
    try:
        df = sp._fetch_from_tachibana(code, from_date, to_date)
        if df is not None and not df.empty:
            tachibana_results[code] = df
    except Exception as e:
        logger.warning(f"Tachibana {code}: {e}")

# --- Phase 2: Stooq（8並列） ---
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def fetch_stooq(code, from_date, to_date):
    sp = stocks_price()
    return code, sp._fetch_from_stooq(code, from_date, to_date)

stooq_results = {}
with ThreadPoolExecutor(max_workers=args.workers) as executor:
    futures = {executor.submit(fetch_stooq, c, from_date, to_date): c for c in codes}
    for future in as_completed(futures):
        code, df = future.result()
        if df is not None and not df.empty:
            stooq_results[code] = df

# --- Phase 3: J-Quants（4並列 + レート制限） ---
jquants_limiter = threading.Semaphore(4)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def fetch_jquants(code, from_date, to_date):
    with jquants_limiter:
        sp = stocks_price()
        return code, sp._fetch_from_jquants(code, from_date, to_date)

jquants_results = {}
with ThreadPoolExecutor(max_workers=args.jquants_workers) as executor:
    futures = {executor.submit(fetch_jquants, c, from_date, to_date): c for c in codes}
    for future in as_completed(futures):
        code, df = future.result()
        if df is not None and not df.empty:
            jquants_results[code] = df

# --- Phase 4: マージ + DuckDB保存（8並列） ---
def merge_and_save(code):
    sp = stocks_price()
    df = merge_with_jquants_priority(
        tachibana_results.get(code),
        stooq_results.get(code),
        jquants_results.get(code),
    )
    if df is not None and not df.empty:
        sp.db.save_stock_prices(code, df)
        return code, True, len(df)
    return code, False, 0

with ThreadPoolExecutor(max_workers=args.workers) as executor:
    futures = {executor.submit(merge_and_save, c): c for c in codes}
    for future in as_completed(futures):
        code, ok, count = future.result()
        # ログ出力 + summary 更新
```

### 2. FTPアップロードを `upload_multiple()` に切り替え

`upload_to_ftp()` 内の1ファイルずつ `upload_stocks_daily()` ループ（L276-288）を、既存の `client.upload_multiple()` に変更。単一FTPS接続で全ファイルをアップロード。

```python
files = []
for code in modified_codes:
    local_path = os.path.join(local_dir, f"{code}.duckdb")
    if os.path.exists(local_path):
        remote_path = f"{client.STOCKS_DAILY_DIR}/{code}.duckdb"
        files.append((local_path, remote_path))

results = client.upload_multiple(files)
```

### 3. CLI 引数を追加

```python
parser.add_argument(
    '--workers', type=int, default=8,
    help='Stooq/DuckDB 並列ワーカー数（デフォルト: 8）'
)
parser.add_argument(
    '--jquants-workers', type=int, default=4,
    help='J-Quants 並列ワーカー数（デフォルト: 4、レート制限考慮）'
)
```

### 4. リトライ戦略

並列化により散発的なネットワークエラーが増えるため、`tenacity` でリトライを追加:

- **Stooq / J-Quants**: 最大3回、指数バックオフ（1秒〜10秒）
- **Tachibana**: 既存のエラーハンドリングを維持（セッション状態があるため安易なリトライは危険）

```
pip install tenacity  # 要追加
```

## 期待効果

| 項目 | 現状 | 改善後 | 備考 |
|------|------|--------|------|
| Tachibana | ~3,800 × 2秒 = ~2時間 | ~2時間（直列維持） | スレッドセーフ問題のため並列化不可 |
| Stooq | ~3,800 × 2秒 = ~2時間 | 8並列 → ~15分 | ステートレスで安全 |
| J-Quants | ~3,800 × 2秒 = ~2時間 | 4並列 → ~30分 | レート制限考慮 |
| マージ+保存 | ~3,800 × 0.5秒 = ~30分 | 8並列 → ~4分 | 銘柄別ファイルで安全 |
| FTPアップロード | 3,800接続 × 2秒 = ~2時間 | 1接続バッチ → ~30分 | `upload_multiple()` 活用 |
| **合計** | **4時間超** | **~3時間** | Tachibana がボトルネック |

> **注**: Tachibana が全体のボトルネックになるが、Stooq/J-Quants/FTP を並列化するだけでも大幅改善。
> 将来 Tachibana API のスレッドセーフ化（`p_no` の `Lock` 保護 + セッション管理改善）が実現すれば ~1.5時間まで短縮可能。

## 検証

```bash
# 少数銘柄で動作確認（各フェーズの動作を確認）
python tasks/update_stocks_price.py --codes 7203,8306,9984 --workers 2 --jquants-workers 2

# dry-run でフェーズ別取得のみテスト
python tasks/update_stocks_price.py --workers 8 --jquants-workers 4 --dry-run

# Stooq のみ並列テスト（Tachibana/J-Quants をスキップ）
python tasks/update_stocks_price.py --codes 7203,8306,9984 --source stooq --workers 4
```

## 将来の追加最適化（対象外）

- Tachibana e-API の `p_no` を `threading.Lock` で保護し、低並列（2-3）で並列化
- `asyncio` + `aiohttp` への移行（I/O バウンドタスクにはスレッドより効率的）
- DuckDB の WAL モードを活用した書き込み最適化