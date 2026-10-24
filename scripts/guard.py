#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
输出守卫 —— 敏感信息外泄的最后一道闸。

在**任何**要写文件、记日志、对外输出之前调用，命中即拦截。

与 redact.py 的区别：
  redact.py  负责「打码后放行」——把敏感值变成 *** 再输出
  guard.py   负责「拦截报警」——发现敏感值就报错，绝不静默放行

两道一起用：先 guard 检查，通过了再 redact 输出。

用法：
    from guard import scan, assert_clean

    hits = scan(text)              # 返回命中的问题列表（空 = 干净）
    assert_clean(text, "写入日志")  # 有命中直接抛 SensitiveLeakError

命令行：
    python scripts/guard.py <文件或目录>       # 扫描
    python scripts/guard.py --stdin            # 扫标准输入
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable

# ---------------- 检测规则 ----------------
# (规则名, 正则, 说明)
_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "MCP_TOKEN",
        re.compile(
            r"(?i)(?:token|access_?token|api_?key|apikey|secret|authorization)"
            r"\s*[:=]\s*[\"']?([A-Za-z0-9\-._~+/]{12,})[\"']?"
        ),
        "疑似 MCP Token / 密钥赋值",
    ),
    (
        "BEARER",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{8,}"),
        "Authorization Bearer 头",
    ),
    (
        "PHONE",
        re.compile(r"(?<!\d)1[3-9]\d[\-\s.]?\d{3,4}[\-\s.]?\d{4}(?!\d)"),
        "手机号",
    ),
    (
        "IDCARD",
        re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}\d{2}\d{2}\d{3}[\dXx](?!\d)"),
        "身份证号",
    ),
    (
        "ORDER",
        re.compile(r"(?<![A-Za-z0-9])(?:ECS)?\d{16,}(?![0-9])"),
        "超长订单号",
    ),
    (
        "PAY_URL",
        re.compile(r"https?://[^\s\"']*(?:pay|payment)[^\s\"']*\?(?:[^\s\"']*sign[^\s\"']*)"),
        "带签名的付款链接",
    ),
    (
        "EMAIL",
        re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
        "邮箱地址",
    ),
    (
        "DOOR",
        re.compile(r"\d{1,4}\s*(?:号楼|栋|单元|室)\s*\d{0,4}\s*(?:室)?"),
        "门牌号",
    ),
]

# 白名单：出现在这些上下文里的匹配不算泄露（示例、占位符、测试值）
_WHITELIST = re.compile(
    r"(?i)(example|placeholder|your_|xxx+|test[-_]?only|fake|dummy|样例|示例|占位|测试用)"
)

# 豁免文件：脱敏工具自身的示例数据是必要的，扫描时跳过
# （这些文件里出现的"敏感值"全是自测用的假数据）
_EXEMPT_FILES: set[str] = set()

# 单行长度上限：超过就截断展示，避免守卫本身把长文贴进日志
_MAX_SNIPPET = 60


class SensitiveLeakError(RuntimeError):
    """检测到敏感信息，拒绝输出。"""


@dataclass
class Hit:
    rule: str
    desc: str
    snippet: str
    line_no: int

    def __str__(self) -> str:
        return f"[{self.rule}] {self.desc} @ 第 {self.line_no} 行: {self.snippet}"


def _snippet(s: str) -> str:
    """命中片段只展示首尾，中间打码——守卫自己也不能回显敏感值。"""
    s = s.strip()
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}***{s[-2:]}"


def scan(text: str) -> list[Hit]:
    """扫描文本，返回所有命中（空列表 = 干净）。"""
    if not text:
        return []
    hits: list[Hit] = []
    for line_no, line in enumerate(str(text).splitlines(), 1):
        if _WHITELIST.search(line):
            continue  # 示例/占位行整行跳过
        for rule, pat, desc in _RULES:
            for m in pat.finditer(line):
                raw = m.group(0)
                # Bearer 规则会命中白名单已排除，这里再兜一层
                if _WHITELIST.search(raw):
                    continue
                hits.append(
                    Hit(
                        rule=rule,
                        desc=desc,
                        snippet=_snippet(raw)[:_MAX_SNIPPET],
                        line_no=line_no,
                    )
                )
    return hits


def assert_clean(text: str, context: str = "输出") -> None:
    """有命中即抛错。用于写文件 / 记日志前的强制校验。"""
    hits = scan(text)
    if hits:
        detail = "\n".join(f"  · {h}" for h in hits)
        raise SensitiveLeakError(
            f"⛔ {context}被拦截：检测到 {len(hits)} 处敏感信息\n{detail}\n"
            f"请先脱敏（redact_text / redact_dict）再输出。"
        )


def scan_file(path: str) -> list[Hit]:
    with open(path, encoding="utf-8", errors="ignore") as f:
        return scan(f.read())


def scan_paths(paths: Iterable[str]) -> dict[str, list[Hit]]:
    """扫描文件或目录，返回 {路径: 命中列表}（只含命中的文件）。"""
    result: dict[str, list[Hit]] = {}
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                if any(seg in root for seg in (".git", "__pycache__", "node_modules")):
                    continue
                for name in files:
                    if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf")):
                        continue
                    fp = os.path.join(root, name)
                    try:
                        hits = scan_file(fp)
                    except OSError:
                        continue
                    if hits:
                        result[fp] = hits
        elif os.path.isfile(p):
            hits = scan_file(p)
            if hits:
                result[p] = hits
    return result


# ---------------- 命令行入口 ----------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stdin":
        data = sys.stdin.read()
        h = scan(data)
        if h:
            print("\n".join(str(x) for x in h))
            sys.exit(1)
        print("clean")
        sys.exit(0)

    if len(sys.argv) > 1:
        found = scan_paths(sys.argv[1:])
        if not found:
            print("✅ 未发现敏感信息")
            sys.exit(0)
        for fp, hits in found.items():
            print(f"\n⛔ {fp}")
            for h in hits:
                print(f"   {h}")
        sys.exit(1)

    print("用法: python guard.py <文件或目录> | --stdin")
    sys.exit(0)
