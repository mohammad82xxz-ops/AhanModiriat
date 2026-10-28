# Windows onedir build: keep the entire dist/AhanModiriat folder together.
a = Analysis(
    ['app.py'], pathex=[], binaries=[], datas=[('static', 'static')], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='AhanModiriat',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=True
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=True, name='AhanModiriat'
)
