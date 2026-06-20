# UTF-8、构建与发布

## UTF-8 contract

桌面 worker transport 是无 BOM UTF-8 JSON Lines：

```text
Renderer → Electron IPC → Python stdin
Python stdout/stderr → streaming UTF-8 decoder → Electron → Renderer
```

### Producer

Python worker 启动时把 `stdin`、`stdout`、`stderr` 重新配置为 UTF-8 strict。Electron 和 worker build 同时设置：

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

### Transport

Node stdout 使用 `Readable.setEncoding("utf8")`，stderr 使用 `StringDecoder("utf8")`。禁止对每个 Buffer chunk 单独调用 `String(chunk)`，因为一个汉字的 UTF-8 字节可能跨 chunk。

### Repository

`.editorconfig` 和 `.gitattributes` 统一文本编码与换行。`scripts/check_text_encoding.py` 检查 tracked text：

- 严格 UTF-8 解码；
- 实际 `U+FFFD`；
- 常见 UTF-8/legacy codepage mojibake。

## 本地构建

```powershell
.venv\Scripts\python -m pytest tests -q --basetemp runs\pytest_tmp_work -o cache_dir=runs\pytest_cache_work
cd apps\desktop
npm test -- --run
npm run build
npm run package
```

`npm run package` 依次构建 renderer、Electron main、PyInstaller onefile worker 和 Windows portable EXE。

## 正式发布门禁

1. 运行编码扫描、完整 Python/frontend tests 和 build。
2. 直接启动 packaged worker，验证中文 progress/error 的 UTF-8 bytes。
3. 启动 portable EXE，走通 Normal 主流程。
4. 检查导出 Markdown/JSON/CSV 编码。
5. 生成 EXE SHA256。
6. 检查 README 图片与链接。
7. 合并到 `main` 后重复关键验证。
8. 创建 annotated tag 和 GitHub Release。

当前 EXE 未配置代码签名证书。Release Notes 必须说明 Windows SmartScreen 可能提示未知发布者，并提供 SHA256 校验文件。
