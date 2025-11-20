## PyPIへのデプロイ方法（Windows）

詳細なリリース手順は `developer-guide.md` の「リリースプロセス」を参照してください。ここでは最小手順のみを記載します。

### 1. 配布物をビルド

```powershell
python -m build
```

### 2. PyPIへアップロード

```powershell
python -m twine upload --repository pypi dist/*
```

アップロード時は PyPI の API トークン（`pypi-` で始まる値）を入力します。

参考: [Packaging projects（公式）](https://packaging.python.org/en/latest/tutorials/packaging-projects/)