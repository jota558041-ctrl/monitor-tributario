---
name: run-monitor-tributario
description: Build, run, and drive Monitor Tributário (FastAPI backend + React/Vite frontend). Use when asked to start the app, run its backend or e2e tests, seed demo data, or screenshot/interact with the running UI.
---

Monitor Tributário is a FastAPI backend (SQLite by default) plus a
React/Vite frontend. Drive it via the project's own Playwright e2e
script, `e2e/fluxo-ui.mjs` — it already logs in, walks all 11 modules,
and saves a screenshot per screen. Don't write a new driver; that one
is the harness.

All paths below are relative to the repo root (`monitor-tributario/`).

This was verified on **macOS 12.7.6 (Monterey), Intel (x86_64)**, with
none of Xcode, Homebrew, a modern Python, or Node preinstalled. Every
command below is one that actually ran clean on that machine. If you're
on a newer macOS or Apple Silicon, the OS-level prerequisites (CLT,
Python, Node) are very likely already satisfied or trivially
`brew install`-able — skip straight to Setup.

## Prerequisites

**Xcode Command Line Tools** (gives you a real `git`, `clang`, `python3`
stub). On Monterey, `softwareupdate -l` — even with `sudo` — does not
list CLT; Apple's live catalog no longer offers it for this OS even
though the package still exists on the CDN. Pull it directly:

```bash
curl -s "https://swscan.apple.com/content/catalogs/others/index-14-13-12-10.16-10.15-10.14-10.13-10.12-10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog.gz" -o catalog.gz && gunzip -f catalog.gz
# product 002-83793 is the last CLT release whose .dist script accepts macOS >=12.0 <13.0
/usr/libexec/PlistBuddy -c "Print :Products:002-83793:Packages" catalog | grep URL
# download each CLTools_*.pkg URL it prints, then, per file:
sudo installer -pkg CLTools_Executables.pkg -target /       # repeat for macOSNMOS_SDK, macOSLMOS_SDK, macOS_SDK, SwiftBackDeploy
sudo xcode-select --switch /Library/Developer/CommandLineTools
```

All 5 packages are genuinely Apple-signed (`pkgutil --check-signature`
shows "Software Update" → "Apple Software Update Certification
Authority" → "Apple Root CA") even though the catalog's legacy SHA1
`Digest` field doesn't match the downloaded bytes — that field is
retired and not meant to be checked anymore; the certificate chain is
the real trust check.

**Python 3.12** — the CLT's bundled `python3` is 3.8.9, too old for
`pandas>=2.2` in `backend/requirements.txt`. Not every 3.12.x patch
ships a macOS installer (3.12.9–3.12.16 don't); 3.12.8 does:

```bash
curl -sL -o python.pkg "https://www.python.org/ftp/python/3.12.8/python-3.12.8-macos11.pkg"
sudo installer -pkg python.pkg -target /
/usr/local/bin/python3.12 --version   # -> Python 3.12.8
```

**Homebrew does not work on this machine** — the official installer
refuses outright (`Homebrew on macOS is only supported on Apple Silicon
processors!`); Homebrew dropped Intel macOS. Don't try it; everything
here is installed by direct download instead.

**Node.js 20 LTS** — current Node (tested: v26) crashes instantly on
Monterey (`dyld: Symbol not found: __libcpp_verbose_abort ... Expected
in: /usr/lib/libc++.1.dylib`) because it's linked against a newer
libc++ than this OS ships. Node 20 doesn't have that problem. No
installer needed — it's a self-contained tarball, extracted to
user space (no `sudo`):

```bash
curl -sL -o node.tar.gz "https://nodejs.org/dist/v20.20.2/node-v20.20.2-darwin-x64.tar.gz"
tar -xzf node.tar.gz
mkdir -p ~/.local/opt ~/.local/bin
mv node-v20.20.2-darwin-x64 ~/.local/opt/node
ln -sf ~/.local/opt/node/bin/node ~/.local/bin/node
ln -sf ~/.local/opt/node/bin/npm  ~/.local/bin/npm
ln -sf ~/.local/opt/node/bin/npx  ~/.local/bin/npx
node --version   # -> v20.20.2
```

`~/.local/bin` is already on `$PATH` by default on this machine; if it
isn't on yours, `export PATH="$HOME/.local/bin:$PATH"`.

## Setup

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install --prefer-binary -r requirements-dev.txt
```

`--prefer-binary` is required: a plain `pip install -r
requirements-dev.txt` resolves `cryptography` to its newest release,
which has no prebuilt wheel for this interpreter/OS combo, and pip
falls back to compiling it from source — which needs Rust/`cargo` and
OpenSSL headers that aren't installed, and fails
(`error: failed-wheel-build-for-install`). `--prefer-binary` makes pip
pick the newest version that *does* have a wheel (landed on
`cryptography-48.0.1`), which satisfies `requirements.txt`'s
`cryptography>=43`.

```bash
cd ../frontend
npm install
```

```bash
cd ../e2e
npm init -y                 # no package.json exists here yet
npm install playwright@1.47.0
npx playwright install chromium
```

Pin Playwright to `1.47.0`. The current release (tested: 1.65.1) fails
with `ERROR: Playwright does not support chromium on mac12` — Monterey
has aged out of its support matrix. 1.47.0's Chromium (129.0.6668.29)
installs and runs fine.

Seed demo data (SQLite, resets on every run):

```bash
cd ../backend
MT_SCHEDULER_ENABLED=false python -m scripts.seed --reset
```

## Run (agent path)

Start both servers in the background, wait for each to answer, then
drive the UI with the project's own e2e script.

```bash
cd backend && source venv/bin/activate
nohup python -m uvicorn app.main:app --port 8000 > /tmp/mt-backend.log 2>&1 &
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8000/api/health >/dev/null && break; sleep 1; done
curl -s http://127.0.0.1:8000/api/health
# -> {"status":"ok","banco":"ok","ambiente":"dev","versao":"0.1.0"}

cd ../frontend
nohup npm run dev > /tmp/mt-frontend.log 2>&1 &
for i in $(seq 1 30); do curl -sf http://127.0.0.1:5173/ >/dev/null && break; sleep 1; done
```

Drive it — this logs in as admin, walks all 11 modules (clientes,
compensações, procurações, situação fiscal, alertas, monitoramento,
fontes, auditoria, importação, usuários, documentos), exercises CRUD,
exports Excel/PDF, and screenshots every screen:

```bash
cd ../e2e
node fluxo-ui.mjs http://127.0.0.1:5173
```

Expect `25/25 etapas OK`. Screenshots land in `e2e/capturas/` as
`01-login.png` through `21-documentos.png` (21 screenshots for 25
steps — a few steps reuse an existing capture). Look at `02-painel.png`
first: it's the dashboard with KPI tiles and charts — if it's blank or
shows a login/error screen, something upstream (backend not seeded,
wrong URL) is wrong.

Stop both servers by freeing their ports (`$!` after `nohup ... &` is
not reliable here since `npm run dev` forks vite as a child):

```bash
lsof -ti:8000 -sTCP:LISTEN | xargs -r kill
lsof -ti:5173 -sTCP:LISTEN | xargs -r kill
```

## Run (human path)

Same backend/frontend background-launch as above, then open
`http://localhost:5173` in a real browser and log in:

| Perfil | E-mail | Senha |
|---|---|---|
| Administrador | `admin@monitortributario.com.br` | `Admin@123456` |
| Analista | `analista@monitortributario.com.br` | `Analista@123456` |
| Auditor (somente leitura) | `auditor@monitortributario.com.br` | `Auditor@123456` |

## Test

Backend (SQLite, no services needed):

```bash
cd backend && source venv/bin/activate
python -m pytest tests/ -q
# -> 85 passed, 8 warnings in ~140s
```

UI/e2e: the `node fluxo-ui.mjs http://127.0.0.1:5173` command in
"Run (agent path)" above *is* the test suite for the frontend — same
command, same 25 steps.

---

## Gotchas

- **`softwareupdate -l` lies on Monterey.** Even `sudo softwareupdate -l`
  reports "No new software available" for Command Line Tools, while the
  package is still live on Apple's CDN. Pull it from the raw catalog
  XML instead (see Prerequisites) — don't conclude CLT is unavailable
  from the `-l` output alone.
- **GitHub CLI's official `.pkg` is unsigned.** `gh_*_macOS_universal.pkg`
  fails `pkgutil --check-signature` ("no usable signature") and
  Gatekeeper rejects it, even though the file is genuine (its SHA256
  matches GitHub's own published checksum). Use the `gh_*_macOS_amd64.zip`
  binary directly instead of the pkg — no Gatekeeper/installer step at
  all for a plain binary run from Terminal.
- **Catalog `Digest` fields are not real integrity checks anymore** on
  Apple's software-update catalogs — a SHA1 mismatch against a
  downloaded CLT package does not mean corruption. Check the code
  signature (`pkgutil --check-signature`) instead.
- **Two unrelated tools (Node, Playwright) both gate on the macOS
  version string, not just the architecture.** Both have a "current"
  release that outright refuses to run/install on `mac12`/Monterey
  regardless of Intel-vs-ARM. If something inexplicably fails only on
  this machine, suspect the macOS-version floor before anything else
  and try an older pinned version.

## Troubleshooting

- **`command not found: timeout`**: macOS doesn't ship GNU `timeout`
  (it's coreutils, not present without Homebrew — which doesn't work
  here either). The readiness-poll loops above use a plain
  `for i in $(seq 1 30); do ... && break; sleep 1; done` instead; don't
  reach for `timeout ... bash -c '...'`.
- **`dyld[...]: Symbol not found: (__ZNSt3__122__libcpp_verbose_abortEPKcz)` when running `node`**:
  Node build is linked against a libc++ newer than Monterey's
  `/usr/lib/libc++.1.dylib` ships. Use Node 20 LTS, not current/latest.
- **`error: failed-wheel-build-for-install` on `cryptography` during
  `pip install -r requirements-dev.txt`**: pip resolved a `cryptography`
  version with no wheel for this Python/OS and tried to compile it
  (needs Rust + OpenSSL headers, not installed). Re-run with
  `pip install --prefer-binary -r requirements-dev.txt`.
- **`ERROR: Playwright does not support chromium on mac12` from
  `npx playwright install chromium`**: pin `playwright@1.47.0` (or
  another pre-2025 release) instead of the latest.
- **`Homebrew on macOS is only supported on Apple Silicon processors!`**:
  expected on this Intel Mac — Homebrew dropped Intel support. Install
  tools by direct download (pattern used throughout this skill) instead
  of reaching for `brew`.
