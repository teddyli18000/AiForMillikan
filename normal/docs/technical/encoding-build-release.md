# Normal Encoding, Build, and Release

## UTF-8 contract

Worker transport is UTF-8 JSON Lines without BOM:

```text
Renderer → Electron IPC → Python stdin
Python stdout/stderr → streaming UTF-8 decoder → Electron → Renderer
```

- The Python worker reconfigures `stdin`, `stdout`, and `stderr` as strict UTF-8.
- Development and packaged workers run with `PYTHONUTF8=1` and
  `PYTHONIOENCODING=utf-8`.
- Node decodes stdout with `setEncoding("utf8")` and stderr with a streaming
  `StringDecoder`. Never call `String(chunk)` per pipe chunk.
- `scripts/check_text_encoding.py` rejects invalid UTF-8, `U+FFFD`, and common
  mojibake in tracked text files.

## Local build

```powershell
cd normal
.venv\Scripts\python -m pytest tests -q
cd apps\desktop
npm test
npm run build
npm run worker:build
npx electron-builder --win portable
```

`worker:build` uses PyInstaller from `normal\.venv` and writes
`dist-worker\millikan-normal-worker.exe`. `electron-builder` copies it into
`resources\worker\`.

## Release gates

1. Encoding scan, full Python suite, frontend suite, TypeScript build.
2. Build the worker and package the portable EXE.
3. Start the packaged worker and verify Chinese progress/error bytes.
4. Launch the portable EXE and walk the Normal workflow.
5. Check exported Markdown/JSON/CSV encoding.
6. Generate the SHA256 file.
7. Create tag `normal-vX.Y.Z` and let `normal-release.yml` publish the Release.

The EXE is unsigned. Release notes must mention the Windows SmartScreen warning
and provide the SHA256 checksum.
