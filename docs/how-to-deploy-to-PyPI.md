## PyPIへのデプロイ方法（Windows / uv）

詳細なリリース手順は `developer-guide.md` の「リリースプロセス」を参照してください。ここでは最小手順のみを記載します。

### 1. 配布物をビルド

```powershell
uv build
```

### 2. PyPIへアップロード

```powershell
uv publish
```

```powershell
uv publish --publish-url https://test.pypi.org/legacy/
```

アップロード時は PyPI の API トークン（`pypi-` で始まる値）を入力します。

環境変数で事前に設定する場合：

```powershell
$env:UV_PUBLISH_TOKEN = "pypi-xxxx..."
uv publish
```

参考:
- [uv build](https://docs.astral.sh/uv/reference/cli/#uv-build)
- [uv publish](https://docs.astral.sh/uv/reference/cli/#uv-publish)
- [Packaging projects（公式）](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
