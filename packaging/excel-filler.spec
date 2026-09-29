# PyInstaller recipe for the downloadable app: `uv run --group build pyinstaller packaging/excel-filler.spec`
# Output: dist/ExcelFiller/ (ExcelFiller.exe and its _internal folder), zipped by the release workflow.
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

datas, binaries, hiddenimports = [], [], []

# Our packages and their files: the window's UI, the organization's settings, the agent's skills.
datas += collect_data_files("excel_filler")
datas += collect_data_files("coding_agent")
hiddenimports += collect_submodules("excel_filler") + collect_submodules("coding_agent")

# Versions read at run time (the app's own version is checked against the minimum version).
for dist in ("excel-filler-desktop-app", "codeagent", "anthropic", "fastapi", "uvicorn", "pydantic",
             "azure-identity", "msal", "pywebview", "openpyxl", "pypdf", "httpx"):
    datas += copy_metadata(dist)

# The local backend: uvicorn chooses its protocols at run time.
hiddenimports += collect_submodules("uvicorn") + collect_submodules("websockets")

# The native window (WebView2 through pythonnet on Windows) and the Windows account sign-in.
for package in ("webview", "pythonnet", "clr_loader", "pymsalruntime", "azure.identity"):
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
    excludes=["tkinter", "matplotlib", "pytest", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ExcelFiller",
    console=False,  # a window app; output goes to the log file (~/.coding-agent/logs)
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ExcelFiller")
