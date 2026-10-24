#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳风格分享图生成器。

产出两种东西：
  1. HTML 卡片（可直接浏览器打开 / 截图 / 转发）
  2. 可选：PNG 图片（需本机有 Playwright 或 Chrome）

品牌规范（2026-10-24 核实，来源见 references/mcd-ad-slogans.md）：
  · 麦当劳红 #DA291C  —— 主色，白底对比度 4.87:1，达 WCAG AA
  · 麦当劳金 #FFC72C  —— 白底仅 1.56:1，**只能做填充/大字/图形，禁止当正文色**
  · 白 #FFFFFF

⚠️ 合规：金拱门 Logo 是注册商标。本脚本**只做视觉风格致敬**（配色 + 抽象拱形），
   不复制官方 Logo 文件，成品带「非官方」标注。

用法：
    from share_card import build_card, save_html, render_png

    html = build_card(
        title="今日麦门",
        items=[("板烧鸡腿堡（去酱）", "391 kcal"), ("小杯玉米杯", "53 kcal")],
        footer="合计 ≈ 444 kcal ｜ 蛋白质 ≈ 25g",
        slogan="我就喜欢",
        literature="成年人的自律，就是在崩溃边缘还点一份低卡套餐。",
    )
    save_html(html, "out/share.html")
"""

from __future__ import annotations

import html as _html
import os
from typing import Iterable, Sequence

# ---- 品牌色（核实值，勿改）----
MCD_RED = "#DA291C"
MCD_GOLD = "#FFC72C"
MCD_YELLOW = "#FFB81C"
MCD_WHITE = "#FFFFFF"
MCD_DARK = "#1A1A1A"
MCD_CREAM = "#FFF8E7"

# 正文色：金色白底不达标，正文一律用深色
BODY_TEXT = MCD_DARK
MUTED_TEXT = "#6B6B6B"


def _esc(s: object) -> str:
    return _html.escape(str(s), quote=True)


def _arches_svg(color: str = MCD_GOLD, height: int = 46) -> str:
    """抽象金拱门图形。

    注意：这是**风格化致敬**，用两条简单拱形曲线表达，不是官方 Logo 的复刻。
    官方 Logo 请勿自行绘制或分发。
    """
    w = int(height * 2.05)
    return f'''<svg width="{w}" height="{height}" viewBox="0 0 205 100"
     xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M6 96 C6 30 40 6 56 6 C72 6 88 30 96 96"
        fill="none" stroke="{color}" stroke-width="13"
        stroke-linecap="round"/>
  <path d="M110 96 C118 30 134 6 150 6 C166 6 199 30 199 96"
        fill="none" stroke="{color}" stroke-width="13"
        stroke-linecap="round"/>
</svg>'''


def build_card(
    *,
    title: str = "今日麦门",
    subtitle: str = "",
    items: Sequence[tuple[str, str]] | None = None,
    footer: str = "",
    literature: str = "",
    slogan: str = "",
    badge: str = "",
    non_official_note: str = "非官方 · 个人分享",
    shot_mode: bool = False,
) -> str:
    """生成麦当劳风格分享卡片 HTML。

    参数：
      title      主标题（如"今日麦门""低卡午餐"）
      subtitle   副标题（如门店名、日期）
      items      [(餐品名, 右侧标注)] 列表，右侧常放热量或价格
      footer    底部汇总行（如"合计 ≈ 444 kcal"）
      literature 麦门文学正文（≤100 字）
      slogan     广告语（如"我就喜欢"），会以金色大字呈现
      badge      右上角角标（如"帮你省了 ¥6.0"）
      shot_mode  截图模式：去掉页面级留白与居中，便于精确截图
    """
    items = list(items or [])

    # 截图模式：body 无 padding、无居中，卡片紧贴左上，方便按内容裁剪
    body_css = (
        "background:#fff;display:block;padding:0;min-height:auto;"
        if shot_mode else
        "background:#E8E2D5;display:flex;align-items:center;"
        "justify-content:center;min-height:100vh;padding:40px 20px;"
    )

    rows = "\n".join(
        f'''      <li class="row">
        <span class="row-name">{_esc(n)}</span>
        <span class="row-val">{_esc(v)}</span>
      </li>'''
        for n, v in items
    )
    rows_block = f'<ul class="list">\n{rows}\n    </ul>' if items else ""

    badge_html = f'<div class="badge">{_esc(badge)}</div>' if badge else ""
    subtitle_html = f'<div class="subtitle">{_esc(subtitle)}</div>' if subtitle else ""
    footer_html = f'<div class="footer">{_esc(footer)}</div>' if footer else ""
    slogan_html = (
        f'<div class="slogan">{_arches_svg(MCD_GOLD, 40)}'
        f'<span class="slogan-text">{_esc(slogan)}</span></div>'
        if slogan else ""
    )
    lit_html = (
        f'<div class="literature">'
        f'<div class="lit-quote">&ldquo;</div>'
        f'<p>{_esc(literature)}</p>'
        f'</div>'
        if literature else ""
    )

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{_esc(title)} · 麦门</title>
<style>
  :root {{
    --mcd-red: {MCD_RED};
    --mcd-gold: {MCD_GOLD};
    --mcd-yellow: {MCD_YELLOW};
    --mcd-white: {MCD_WHITE};
    --mcd-cream: {MCD_CREAM};
    --text: {BODY_TEXT};
    --muted: {MUTED_TEXT};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    {body_css}
    font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB",
                 "Noto Sans SC", system-ui, -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}

  /* 卡片本体：红底 + 金拱门，麦当劳经典配色关系 */
  .card {{
    width: 720px;
    max-width: 100%;
    background: var(--mcd-red);
    border-radius: {'0' if shot_mode else '28px'};
    overflow: hidden;
    box-shadow: {'none' if shot_mode else '0 18px 50px rgba(0,0,0,.28)'};
    position: relative;
  }}

  /* 顶部金色装饰条 */
  .top-stripe {{
    height: 12px;
    background: linear-gradient(90deg,
      var(--mcd-gold) 0%, var(--mcd-yellow) 50%, var(--mcd-gold) 100%);
  }}

  .head {{
    padding: 40px 48px 26px;
    position: relative;
  }}

  .arches {{ margin-bottom: 22px; }}

  h1 {{
    font-size: 46px;
    font-weight: 900;
    color: var(--mcd-white);
    letter-spacing: -.5px;
    line-height: 1.15;
  }}

  .subtitle {{
    margin-top: 10px;
    font-size: 16px;
    color: rgba(255,255,255,.82);
    font-weight: 500;
  }}

  .badge {{
    position: absolute;
    top: 40px;
    right: 48px;
    background: var(--mcd-gold);
    color: var(--mcd-red);
    font-size: 15px;
    font-weight: 800;
    padding: 9px 18px;
    border-radius: 999px;
    box-shadow: 0 4px 12px rgba(0,0,0,.18);
    white-space: nowrap;
  }}

  /* 内容区：奶白底，保证文字对比度达标 */
  .body {{
    background: var(--mcd-cream);
    margin: 0 22px 22px;
    border-radius: 20px;
    padding: 32px 40px 34px;
  }}

  .list {{ list-style: none; }}

  .row {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 20px;
    padding: 14px 0;
    border-bottom: 1px dashed rgba(218,41,28,.22);
  }}
  .row:last-child {{ border-bottom: none; }}

  .row-name {{
    font-size: 21px;
    font-weight: 700;
    color: var(--text);
    line-height: 1.4;
  }}

  .row-val {{
    font-size: 19px;
    font-weight: 800;
    color: var(--mcd-red);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }}

  .footer {{
    margin-top: 22px;
    padding-top: 20px;
    border-top: 3px solid var(--mcd-gold);
    font-size: 22px;
    font-weight: 800;
    color: var(--text);
    letter-spacing: .3px;
  }}

  .slogan {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 28px;
    padding-top: 24px;
    border-top: 1px dashed rgba(218,41,28,.22);
  }}

  .slogan-text {{
    font-size: 27px;
    font-weight: 900;
    color: var(--mcd-red);
    letter-spacing: 1px;
  }}

  .literature {{
    margin-top: 26px;
    background: var(--mcd-red);
    border-radius: 16px;
    padding: 26px 30px 28px;
    position: relative;
  }}

  .lit-quote {{
    font-size: 54px;
    line-height: .6;
    color: var(--mcd-gold);
    font-family: Georgia, serif;
    margin-bottom: 12px;
  }}

  .literature p {{
    font-size: 19px;
    line-height: 1.85;
    color: var(--mcd-white);
    font-weight: 500;
    letter-spacing: .3px;
  }}

  .foot {{
    padding: 0 48px 26px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 13px;
    color: rgba(255,255,255,.72);
  }}

  @media print {{
    body {{ background: none; padding: 0; }}
    .card {{ box-shadow: none; }}
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="top-stripe"></div>
    <div class="head">
      {badge_html}
      <div class="arches">{_arches_svg(MCD_GOLD, 46)}</div>
      <h1>{_esc(title)}</h1>
      {subtitle_html}
    </div>
    <div class="body">
      {rows_block}
      {footer_html}
      {slogan_html}
      {lit_html}
    </div>
    <div class="foot">
      <span>{_esc(non_official_note)}</span>
      <span>麦门超级管家</span>
    </div>
  </div>
</body>
</html>
'''


def save_html(html: str, path: str) -> str:
    """写出 HTML 文件，返回绝对路径。"""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.abspath(path)


def _trim_png_whitespace(path: str, *, bg=None, tol: int = 10) -> bool:
    """裁掉 PNG 四周的纯背景留白。纯标准库实现，无第三方依赖。

    做法：自己解 PNG（8bit RGB/RGBA）→ 找内容边界 → 重新编码。
    失败则返回 False（调用方保留原图）。

    bg 为 None 时**自动取左上角像素作为背景色**——页面背景可能是白、
    也可能是米灰（#E8E2D5），硬编码白色会裁不掉，导致输出一张
    大留白的图。自动取样对两种底色都成立。
    """
    import struct
    import zlib

    try:
        raw = open(path, "rb").read()
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            return False

        pos, w, h, ct = 8, None, None, None
        idat = b""
        while pos < len(raw):
            ln = struct.unpack(">I", raw[pos:pos + 4])[0]
            typ = raw[pos + 4:pos + 8]
            data = raw[pos + 8:pos + 8 + ln]
            if typ == b"IHDR":
                w, h, bd, ct = struct.unpack(">IIBB", data[:10])
                if bd != 8 or ct not in (2, 6):
                    return False          # 只处理 8bit RGB/RGBA
            elif typ == b"IDAT":
                idat += data
            elif typ == b"IEND":
                break
            pos += 12 + ln

        if not w or not h:
            return False

        ch = 3 if ct == 2 else 4
        px = bytearray(zlib.decompress(idat))
        stride = w * ch

        # 反滤波
        def paeth(a, b, c):
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

        prev = bytearray(stride)
        out = bytearray()
        for y in range(h):
            f = px[y * (stride + 1)]
            line = bytearray(px[y * (stride + 1) + 1: y * (stride + 1) + 1 + stride])
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                v = line[x]
                if f == 1:
                    v = (v + a) & 0xFF
                elif f == 2:
                    v = (v + b) & 0xFF
                elif f == 3:
                    v = (v + ((a + b) >> 1)) & 0xFF
                elif f == 4:
                    v = (v + paeth(a, b, c)) & 0xFF
                line[x] = v
            out += line
            prev = line

        # 背景色：默认取**右下角**像素。
        # 不能用左上角——截图模式下卡片贴左上，左上角是卡片内容（金色条/红底），
        # 取它会得到一个"错误背景色"，导致整幅图都被判成内容，裁不掉任何空白。
        # 右下角在贴左上的布局里必然是空白区。
        if bg is None:
            i = ((h - 1) * w + (w - 1)) * ch
            bg = (out[i], out[i + 1], out[i + 2])

        def is_bg(x, y):
            i = (y * w + x) * ch
            return all(abs(out[i + k] - bg[k]) <= tol for k in range(3))


        # 找边界
        top = 0
        while top < h and all(is_bg(x, top) for x in range(w)):
            top += 1
        bottom = h - 1
        while bottom > top and all(is_bg(x, bottom) for x in range(w)):
            bottom -= 1
        left = 0
        while left < w and all(is_bg(left, y) for y in range(top, bottom + 1)):
            left += 1
        right = w - 1
        while right > left and all(is_bg(right, y) for y in range(top, bottom + 1)):
            right -= 1

        nw, nh = right - left + 1, bottom - top + 1
        if nw <= 0 or nh <= 0 or (nw == w and nh == h):
            return False

        # 重新编码
        rows = bytearray()
        for y in range(top, bottom + 1):
            rows.append(0)
            i = (y * w + left) * ch
            rows += out[i: i + nw * ch]

        def chunk(typ, data):
            return (struct.pack(">I", len(data)) + typ + data
                    + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", nw, nh, 8, ct, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
               + chunk(b"IEND", b""))
        open(path, "wb").write(png)
        return True
    except Exception:
        return False


def render_png(html_path: str, png_path: str, *, width: int = 720,
               html: str | None = None) -> str | None:
    """把 HTML 渲染成 PNG，并自动裁掉四周空白。

    优先 Playwright（能按元素精确截图）；否则用系统 Chrome/Edge 截大图后裁剪。
    都没有则返回 None，调用方应降级为"给 HTML 让用户自己截图"。
    """
    # ① Playwright
    try:
        from playwright.sync_api import sync_playwright  # type: ignore

        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": width, "height": 900},
                            device_scale_factor=2)
            pg.goto("file:///" + os.path.abspath(html_path).replace("\\", "/"))
            pg.wait_for_timeout(300)
            card = pg.query_selector(".card")
            (card or pg).screenshot(path=png_path)
            b.close()
        return os.path.abspath(png_path)
    except Exception:
        pass

    # ② 系统 Chrome / Edge：截大图 → 裁空白
    import shutil
    import subprocess
    import tempfile

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    exe = next((c for c in candidates if os.path.exists(c)), None)
    if not exe:
        exe = shutil.which("chrome") or shutil.which("msedge")
    if not exe:
        return None

    # 用截图模式重新渲染一份（无留白、贴左上），避免裁到页面背景
    tmp_html = None
    source_html = html
    if source_html is None:
        try:
            with open(html_path, encoding="utf-8") as f:
                source_html = f.read()
        except OSError:
            source_html = None
    if source_html is not None:
        try:
            shot_html = source_html.replace(
                "background:#E8E2D5;display:flex;align-items:center;"
                "justify-content:center;min-height:100vh;padding:40px 20px;",
                "background:#fff;display:block;padding:0;min-height:auto;",
            ).replace("border-radius: 28px", "border-radius: 0").replace(
                "box-shadow: 0 18px 50px rgba(0,0,0,.28)", "box-shadow: none"
            )
            fd, tmp_html = tempfile.mkstemp(suffix=".html")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(shot_html)
            src = tmp_html
        except Exception:
            src = html_path
    else:
        src = html_path

    # 截图高度：给足余量即可，后续由 _trim_png_whitespace 精确裁掉空白。
    # 不要设得过大（如 3000），否则中间图过大、且 2x 缩放后容易撞浏览器上限。
    shot_height = 1400

    try:
        subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=2",
             f"--screenshot={os.path.abspath(png_path)}",
             f"--window-size={width},{shot_height}",
             "file:///" + os.path.abspath(src).replace("\\", "/")],
            check=True, capture_output=True, timeout=90,
        )
        ok = os.path.exists(png_path)
    except Exception:
        ok = False
    finally:
        if tmp_html and os.path.exists(tmp_html):
            try:
                os.remove(tmp_html)
            except OSError:
                pass

    if not ok:
        return None

    _trim_png_whitespace(png_path)
    return os.path.abspath(png_path)
