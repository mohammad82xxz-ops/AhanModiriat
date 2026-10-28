# -*- coding: utf-8 -*-
"""Token-level WCAG contrast smoke tests for light and dark themes."""
import re
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_contrast_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def custom_properties(block):
    return {name:value.strip() for name,value in re.findall(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);",block)}


def resolve(name, values, fallback, seen=None):
    seen=set() if seen is None else seen
    if name in seen:
        raise AssertionError(f"cyclic CSS token reference: {name}")
    seen.add(name)
    value=values.get(name,fallback.get(name))
    assert value is not None, f"missing CSS token {name}"
    match=re.fullmatch(r"var\((--[A-Za-z0-9_-]+)\)",value.strip())
    return resolve(match.group(1),values,fallback,seen) if match else value.strip()


def luminance(color):
    match=re.fullmatch(r"#([0-9a-fA-F]{6})",color)
    assert match, f"expected six-digit RGB color, got {color!r}"
    channels=[int(match.group(1)[i:i+2],16)/255 for i in (0,2,4)]
    linear=[x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4 for x in channels]
    return 0.2126*linear[0]+0.7152*linear[1]+0.0722*linear[2]


def contrast(foreground,background):
    a,b=luminance(foreground),luminance(background)
    return (max(a,b)+0.05)/(min(a,b)+0.05)


def main():
    app.init()
    root=Path(app.STATIC_DIR)
    token_css=(root/"tokens.css").read_text(encoding="utf-8")
    app_css=(root/"app.css").read_text(encoding="utf-8")
    root_match=re.search(r":root\s*\{(.*?)\}",token_css,re.S)
    dark_match=re.search(r'\[data-theme="dark"\]\s*\{(.*?)\}',token_css,re.S)
    assert root_match and dark_match
    light=custom_properties(root_match.group(1))
    dark=custom_properties(dark_match.group(1))
    pairs=(
        ("--text-primary","--surface",4.5),
        ("--text-secondary","--surface",4.5),
        ("--text-muted","--surface",4.5),
        ("--brand","--surface",4.5),
        ("--button-text","--brand",4.5),
        ("--success-text","--success-bg",4.5),
        ("--warning-text","--warning-bg",4.5),
        ("--danger-text","--danger-bg",4.5),
        ("--info-text","--info-bg",4.5),
    )
    for theme,overrides in (("light",{}),("dark",dark)):
        values={**light,**overrides}
        for fg,bg,threshold in pairs:
            fg_color=resolve(fg,values,light)
            bg_color=resolve(bg,values,light)
            ratio=contrast(fg_color,bg_color)
            assert ratio>=threshold,(theme,fg,bg,round(ratio,2),threshold)
        focus=contrast(resolve("--focus",values,light),resolve("--surface",values,light))
        assert focus>=3.0,(theme,"focus indicator",round(focus,2))
    assert ":focus-visible" in app_css
    assert "prefers-reduced-motion" in app_css
    assert "min-height:var(--touch-min)" in app_css
    print("ACCESSIBILITY TOKEN CONTRAST TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()
