# PyInstaller recipe for the downloadable app: `uv run --group build pyinstaller packaging/comptaia.spec`
# Output: dist/ComptaIA/ (ComptaIA.exe on Windows and its _internal folder), zipped by the build workflow.
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

datas, binaries, hiddenimports = [], [], []

# Our packages and their files: the window's UI (excel_filler/desktop/static), the agent's skills and prompts.
datas += collect_data_files("excel_filler")
datas += collect_data_files("coding_agent")
hiddenimports += collect_submodules("excel_filler") + collect_submodules("coding_agent")

# Versions read at run time.
for dist in ("excel-filler-desktop-app", "codeagent", "anthropic", "fastapi", "uvicorn", "pydantic", "pywebview",
             "openpyxl", "pypdfium2", "httpx", "keyring"):
    try:
        datas += copy_metadata(dist)
    except Exception:  # a dependency that this build does not have
        pass

# The local backend: uvicorn chooses its protocols at run time. keyring picks its backend by name.
hiddenimports += collect_submodules("uvicorn") + collect_submodules("websockets") + collect_submodules("keyring.backends")

# The native window (WebView2 through pythonnet on Windows) and PDF page drawing (a native library).
for package in ("webview", "pythonnet", "clr_loader", "pypdfium2", "pypdfium2_raw"):
    try:
        d, b, h = collect_all(package)
    except Exception:  # not installed on this platform (e.g. pythonnet off Windows)
        continue
    datas, binaries, hiddenimports = datas + d, binaries + b, hiddenimports + h

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],  # SPECPATH: this file's folder, wherever the build runs from
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "pytest", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ComptaIA",
    console=False,  # a window app; output goes to the log file (~/.coding-agent/logs)
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ComptaIA")
