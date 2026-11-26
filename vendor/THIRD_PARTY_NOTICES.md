# 第三方元件聲明 / Third-party software in this folder

**中文摘要**：這個資料夾的 `heic-decoder.html` 內含一個第三方元件 libheif-js 1.23.5，用來在 Chrome、Edge、Firefox 這些不能直接顯示 HEIC 的瀏覽器裡解碼 iPhone 的 HEIC 照片。它採用 LGPL-3.0 授權，原樣收錄、沒有修改，授權全文在同資料夾的 `LICENSE-libheif-js.txt`。本專案其餘檔案都不含第三方程式碼。

`heic-decoder.html` contains one third-party component. Nothing else in this repository is third-party code.

| | |
|---|---|
| Component | libheif-js 1.23.5, file `libheif-wasm/libheif-bundle.js` (2,044,206 bytes) |
| What it is | An Emscripten (WebAssembly) build of libheif with the libde265 HEVC decoder. The library reports libheif 1.23.5 and libde265 1.0.15 |
| Obtained from | The npm registry, package `libheif-js`, version `1.23.5` |
| SHA-256 of that file | `074b2b55ef3de477ba9f794ca381f3f0324c1cba8c91b4af07395f39c22d54cc` |
| Licence | GNU Lesser General Public License version 3 (LGPL-3.0). Full text, as shipped with the package: `LICENSE-libheif-js.txt` in this folder |
| Changes | None. The file is embedded byte for byte as a text block of `heic-decoder.html` |

## Where the source code is

- libheif-js, the build scripts and JavaScript wrapper: <https://github.com/catdad-experiments/libheif-js>
- libheif: <https://github.com/strukturag/libheif>
- libde265: <https://github.com/strukturag/libde265>

Take the releases that match the versions in the table above.

## How it is used

`index.html` loads `heic-decoder.html` only when a HEIC photo is added and the browser cannot show it. The page runs in a frame with `sandbox="allow-scripts"` and its own policy `default-src 'none'`: it receives the bytes of one photo and answers with pixels. It has no network access and cannot reach the tool, its storage or other files. `docs/SECURITY_REVIEW.md` describes this and `tests/check_heic.py` checks it in a real browser.

The only code of this project inside `heic-decoder.html` is the small glue script, whose source is `tools/heic_decoder_glue.js`.

## Checking or replacing the library

- `node tools/build_heic_decoder.mjs --check` verifies that the committed page holds exactly the file with the hash above and the glue script from `tools/`.
- To use another libheif build, your own included: put the name, version and SHA-256 of its `libheif-bundle.js` into `LIB` in `tools/build_heic_decoder.mjs`, then run `node tools/build_heic_decoder.mjs <path to libheif-bundle.js>`. Nothing else has to change, because the tool talks to this page only through the message format described at the top of `tools/heic_decoder_glue.js`.
