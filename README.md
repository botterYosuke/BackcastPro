# <img src="https://raw.githubusercontent.com/botterYosuke/BackcastPro/main/docs/img/logo.drawio.svg" alt="BackcastPro Logo" width="40" height="24"> BackcastPro

トレーディング戦略のためのPythonバックテストライブラリ。

## インストール（Windows）

### PyPIから（エンドユーザー向け）

```powershell
python -m pip install BackcastPro
```

### 開発用インストール

開発用に、リポジトリをクローンして開発モードでインストールします。

```powershell
git clone <repository-url>
cd BackcastPro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install -r requirements.txt
```

**開発モードインストール（python -m pip install -e .）**
- プロジェクトを開発モードでインストールします
- `src` ディレクトリが自動的に Python パスに追加されます

## 使用方法

```python
from BackcastPro import *

# ここにトレーディング戦略の実装を記述
```

## ドキュメント

- [ドキュメント一覧](https://github.com/botterYosuke/BackcastPro/blob/main/docs/index.md)

## バグ報告 / サポート

- バグ報告や要望は GitHub Issues へ
- 質問は Discord コミュニティへ（[招待リンク](https://discord.gg/fzJTbpzE)）
- 使い方はドキュメントをご参照ください

