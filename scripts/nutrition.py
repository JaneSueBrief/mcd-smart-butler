#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOON (Token-Oriented Object Notation) 营养数据解析器。

麦当劳 MCP 的 list-nutrition-foods 为降低 token 消耗，返回 TOON 而非标准 JSON：

    [1]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
      猪柳麦满分,null,1288,308,16,16,24,781,213

首行声明记录数 [N] 与字段名 {a,b,c}:，其后每行一条记录，逗号分隔。

用法：
    from nutrition import parse_toon, load_from_mcp_result, lookup, sum_nutrition

    foods = load_from_mcp_result(raw_mcp_response)
    print(lookup(foods, "猪柳麦满分"))
"""

from __future__ import annotations

import json
import re
from typing import Any

# 营养字段 -> 中文名 / 单位
FIELD_META: dict[str, tuple[str, str]] = {
    "energyKj": ("能量", "kJ"),
    "energyKcal": ("热量", "kcal"),
    "protein": ("蛋白质", "g"),
    "fat": ("脂肪", "g"),
    "carbohydrate": ("碳水化合物", "g"),
    "sodium": ("钠", "mg"),
    "calcium": ("钙", "mg"),
}

_HEADER_RE = re.compile(r"^\[(\d+)\]\{([^}]*)\}\s*:?\s*$")
_NULLS = {"null", "NULL", "None", "none", "", "-"}

# 麦当劳 MCP 把真实响应包在给 LLM 看的 Markdown 说明里，形如：
#   # API Response Information
#   ... 字段说明 ...
#   ## Original Response
#
#   {"success":true,...,"data":"[160]{...}:\n  ..."}
# 需要先把 "## Original Response" 之后的 JSON 抠出来。
_ORIGINAL_RE = re.compile(
    r"##\s*Original\s*Response\s*(.*)", re.IGNORECASE | re.DOTALL
)


def _split_row(line: str) -> list[str]:
    """按逗号切分一行记录。TOON 里字段值不含逗号，直接 split 即可。"""
    return [c.strip() for c in line.split(",")]


def _to_number(raw: str) -> float | int | None:
    if raw in _NULLS:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    return int(val) if val.is_integer() else val


def parse_toon(text: str) -> list[dict[str, Any]]:
    """解析 TOON 文本为记录列表。

    非 TOON 内容（例如已经是 JSON）会尝试按 JSON 解析，失败则返回空列表。
    """
    if not text or not text.strip():
        return []

    stripped = text.strip()

    # 兼容：有些调用方可能已经拿到 JSON 字符串
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            data = json.loads(stripped)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data
        except json.JSONDecodeError:
            pass

    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if not lines:
        return []

    m = _HEADER_RE.match(lines[0].strip())
    if not m:
        # 无表头，无法确定字段名
        return []

    fields = [f.strip() for f in m.group(2).split(",") if f.strip()]
    records: list[dict[str, Any]] = []

    for line in lines[1:]:
        cells = _split_row(line)
        if len(cells) != len(fields):
            # 字段数不匹配，跳过（可能是空行或尾部噪声）
            continue
        rec: dict[str, Any] = {}
        for name, cell in zip(fields, cells):
            rec[name] = _to_number(cell) if name != "productName" and name != "nutritionDescription" else (None if cell in _NULLS else cell)
        records.append(rec)

    return records


def _extract_data_field(payload: Any) -> str:
    """从 MCP 响应中取出承载 TOON 的 data 字段。

    真实响应形态（实测 2026-10-24）：

        {"jsonrpc":"2.0","id":1,"result":{"content":[{"text":
            "# API Response Information\\n\\n...\\n## Original Response\\n\\n"
            '{"success":true,"code":200,"data":"[160]{productName,...}:\\n  猪柳麦满分,..."}'
        }]}}

    即：content[0].text 是 Markdown 说明，说明末尾嵌了真正的 JSON 响应，
    其 data 字段才是 TOON 文本。逐层剥开。
    """
    if isinstance(payload, str):
        text = payload
        # ① 剥 Markdown 外壳：取 "## Original Response" 之后的内容
        m = _ORIGINAL_RE.search(text)
        if m:
            text = m.group(1).strip()
            # 之后可能还有 markdown 代码围栏
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text).strip()

        # ② 此时若是 JSON 对象字符串，继续递归
        if text.startswith("{"):
            try:
                return _extract_data_field(json.loads(text))
            except json.JSONDecodeError:
                pass

        return text

    if isinstance(payload, dict):
        # {"success":true,"data":"<TOON>"}
        if isinstance(payload.get("data"), str):
            return payload["data"]

        # JSON-RPC：{"result":{"content":[{"text":"..."}]}}
        for container_key in ("result", "content"):
            container = payload.get(container_key)
            if container is None:
                continue
            if isinstance(container, dict):
                inner = container.get("content")
                if isinstance(inner, list):
                    for part in inner:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            got = _extract_data_field(part["text"])
                            if got:
                                return got
            elif isinstance(container, list):
                for part in container:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        got = _extract_data_field(part["text"])
                        if got:
                            return got

    return ""


def load_from_mcp_result(payload: Any) -> list[dict[str, Any]]:
    """从各种形态的 MCP 响应中解析出营养记录。

    支持：
      - TOON 纯文本
      - {"success":true,"data":"<TOON>"} 的 JSON 字符串
      - JSON-RPC {"result":{"content":[{"text":"<Markdown 说明>"}]}}
        其中 Markdown 里嵌着 {"success":true,"data":"<TOON>"}
      - 上述任意组合的嵌套
    """
    text = _extract_data_field(payload)
    if not text:
        return []
    return parse_toon(text)


# 口语同义词归一：用户说"零度可乐"，官方叫"无糖可口可乐"
_SYNONYMS = (
    ("零度", "无糖"),
    ("无糖", "无糖"),
    ("可口可乐", "可乐"),
    ("百事可乐", "可乐"),
    ("鸡腿汉堡", "鸡腿堡"),
    ("汉堡包", "汉堡"),
)

# 规格词序归一：菜单写"玉米杯(小)"，营养表写"小杯玉米杯"
# 统一成"小杯XX"的形式，两边就都能对上
_SIZE_RE = re.compile(r"[（(]\s*([大小中])\s*[）)]\s*$")


def _normalize_size(n: str) -> str:
    """把「XX(小)」这类尾缀规格，转成营养表的「小杯XX」写法。

    例：玉米杯(小) -> 小杯玉米杯 ；薯条(大) -> 大杯薯条

    注意：不能因为 base 以「杯」结尾就跳过加规格词——"玉米杯"的「杯」
    是品名的一部分（玉米杯），不是量词；漏掉规格会让"玉米杯(小)"
    退化成"玉米杯"，反而匹配不上营养表的"小杯玉米杯"。
    只有 base 本身已经以「大/小/中杯」开头时才算已归一，直接返回。
    """
    m = _SIZE_RE.search(n)
    if not m:
        return n
    size = m.group(1)
    base = n[:m.start()].strip()
    if not base:
        return n
    if base.startswith(("大杯", "小杯", "中杯")):
        return base
    return f"{size}杯{base}"


def _apply_synonyms(n: str) -> str:
    for src, dst in _SYNONYMS:
        n = n.replace(src, dst)
    return n


def _norm(name: str) -> str:
    """归一化餐品名，便于模糊匹配。

    处理：
    - 去掉所有空白
    - 去掉 _1547 这类内部后缀
    - 全角括号转半角
    - 规格词序归一（玉米杯(小) -> 小杯玉米杯）
    - 连接符归一（麦辣鸡翅-2块 -> 麦辣鸡翅2块）
    - 口语同义词归一
    """
    n = re.sub(r"[\s\u3000]", "", name or "")
    n = re.sub(r"_[0-9]+$", "", n)
    n = n.replace("（", "(").replace("）", ")")
    n = _normalize_size(n)
    # 连接符统一去掉：营养表用"麦辣鸡翅-2块"，菜单用"麦辣鸡翅2块"
    n = n.replace("-", "").replace("—", "").replace("–", "")
    return _apply_synonyms(n)


# 名称中的"区分性修饰词"。查询词若不含这些词，就不能匹配含这些词的候选，
# 否则 "零度可乐" 会匹配到 "可乐"（差 147 kcal），"玉米杯" 会匹配到 "大杯玉米杯"。
_QUALIFIERS = (
    "零度", "无糖", "大杯", "小杯", "中杯", "迷你", "双层", "三层",
    "大", "小", "中", "冰", "热", "加", "去",
)


def _qualifier_signature(name: str) -> frozenset[str]:
    """提取名称里的区分性修饰词集合。"""
    n = _norm(name)
    return frozenset(q for q in _QUALIFIERS if q in n)


def _score(query: str, candidate: str) -> int | None:
    """给候选打分，分越高越合适。

    返回 `None` 表示**毫无文字关联**（应直接剔除）。
    返回整数表示有关联；分数可能为负——那说明候选缺了关键修饰词
    （如查询"玉米杯"、候选"大杯玉米杯"），属于"相关但不确定"，
    应保留在候选列表里让用户确认，而不是当成无关项丢掉。

    注意：不要把"无关"编码成 -1 之类的低分，否则会被修饰词扣分
    （可低至 -60）压过去，导致相关项反被过滤。
    """
    q = _norm(query)
    c = _norm(candidate)
    if not q or not c:
        return None

    qsig = _qualifier_signature(q)
    csig = _qualifier_signature(c)
    extra = csig - qsig          # 候选多出来的修饰词
    missing = qsig - csig        # 候选缺失的修饰词

    if q == c:
        base = 1000
    elif c.startswith(q):
        base = 500
    elif q.startswith(c):
        base = 300
    elif q in c:
        base = 250
    elif c in q:
        base = 200
    else:
        # 无任何匹配关系 —— 判为无关
        return None

    # 长度越接近越好（最多扣 50）
    base -= min(50, abs(len(c) - len(q)) * 5)
    # 候选多出修饰词：每个扣 150（足以让 "可乐" 输给 "零度可乐"）
    base -= 150 * len(extra)
    # 候选缺修饰词：每个扣 200（"零度可乐" 绝不该匹配 "可乐"）
    base -= 200 * len(missing)

    return base


def lookup(
    foods: list[dict[str, Any]],
    name: str,
    *,
    exact: bool = False,
    min_score: int = 1,
) -> dict[str, Any] | None:
    """按名称查一条营养记录，返回**最合适**的一条。

    exact=True 时只做归一化精确匹配。
    否则按 `_score` 打分取最高分；最高分低于 min_score 视为**不确定**，返回 None
    （此时应改用 `lookup_or_ask` 让用户确认，而不是硬猜）。

    min_score 默认 1：得分 <= 0 说明候选缺了关键修饰词（如"玉米杯"缺"大/小杯"），
    不确定就不返回，避免给出错误热量。
    """
    target = _norm(name)
    if not target:
        return None

    if exact:
        for rec in foods:
            if _norm(rec.get("productName", "")) == target:
                return rec
        return None

    best: dict[str, Any] | None = None
    best_score: int | None = None
    for rec in foods:
        s = _score(name, rec.get("productName", ""))
        if s is None:
            continue
        if best_score is None or s > best_score:
            best_score, best = s, rec

    if best is None or best_score is None or best_score < min_score:
        return None
    return best


def candidates(
    foods: list[dict[str, Any]],
    name: str,
    *,
    limit: int = 8,
) -> list[tuple[int, dict[str, Any]]]:
    """返回所有**有关联**的候选（按得分降序）。

    用途：当 `lookup` 返回 None 或需要让用户确认规格时（例如"玉米杯"对应
    "大杯玉米杯"还是"小杯玉米杯"），列出候选让用户选，而不是瞎猜一个。

    判定标准：`_score` 返回 `None` 表示毫无文字关联，剔除；
    其余（含因缺修饰词而被扣成负分的）都算相关候选，保留供用户确认。
    """
    scored: list[tuple[int, dict[str, Any]]] = []
    seen: set[str] = set()
    for rec in foods:
        pname = rec.get("productName", "")
        # 官方数据源存在同名重复条目，按归一化名去重
        key = _norm(pname)
        if key in seen:
            continue
        s = _score(name, pname)
        if s is not None:
            seen.add(key)
            scored.append((s, rec))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def lookup_or_ask(
    foods: list[dict[str, Any]],
    name: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """查营养数据，是"确定命中"还是"需要用户确认"。

    返回 (命中记录 或 None, 候选名称列表)：
      - 命中记录非 None  → 可直接使用
      - 命中为 None 且候选非空 → 让用户从候选里选（如"玉米杯"→大杯/小杯）
      - 两者都空 → 官方营养表未收录该餐品，如实告知
    """
    top = candidates(foods, name, limit=6)
    if not top:
        return None, []

    best_score, best_rec = top[0]

    # 最优必须"确定"（得分 > 0），且要么唯一，要么明显领先第二名
    if best_score > 0 and (len(top) == 1 or best_score - top[1][0] >= 150):
        return best_rec, []

    return None, [rec.get("productName", "") for _, rec in top]


def sum_nutrition(records: list[dict[str, Any]]) -> dict[str, Any]:
    """把多条营养记录相加，返回合计。

    缺失字段按 0 计，同时在 `_missing` 里列出哪些餐品缺了哪些字段，
    便于如实告知用户"该数据官方未提供"。
    """
    total: dict[str, Any] = {k: 0 for k in FIELD_META}
    missing: list[str] = []

    for rec in records:
        if not rec:
            continue
        pname = rec.get("productName", "未知餐品")
        for field in FIELD_META:
            val = rec.get(field)
            if val is None:
                missing.append(f"{pname}.{FIELD_META[field][0]}")
            else:
                total[field] += val

    # 整型化
    for k, v in total.items():
        if isinstance(v, float) and v.is_integer():
            total[k] = int(v)

    total["_missing"] = missing
    return total


def format_summary(total: dict[str, Any], *, note: str = "") -> str:
    """把合计格式化成可读的一行摘要。"""
    parts = []
    for field, (cn, unit) in FIELD_META.items():
        val = total.get(field)
        if val:
            parts.append(f"{cn} {val}{unit}")
    line = " ｜ ".join(parts) if parts else "无可用营养数据"
    if note:
        line += f"\n{note}"
    return line


# ---------------- 人群分型 ----------------
#
# ⚠️ 定位：这是「按官方营养数据做的参考搭配」，不是医疗或营养处方。
#    所有分型都必须在输出时附带免责声明；涉及疾病的必须提示遵医嘱。
#
# 区间依据：中国居民膳食指南对成人一餐的常见建议（约 1/3 日需）+ 常见减脂/增肌
#          实践区间，以及儿童餐的常见份量。**属通行实践区间，非官方规定。**

PROFILES: dict[str, dict[str, Any]] = {
    "adult": {
        "name": "成人日常",
        "kcal": (500, 700),
        "protein_min": 20,
        "notes": "正常一餐，不用刻意控制",
    },
    "kid": {
        "name": "儿童（3–12 岁）",
        "kcal": (300, 500),
        "protein_min": 12,
        "notes": "份量减半，避开高钠（钠 > 800mg 的慎选）",
        "sodium_max": 800,
    },
    "fitness": {
        "name": "健身增肌",
        "kcal": (600, 900),
        "protein_min": 30,
        "notes": "蛋白质优先，可上浮热量；少油炸，多烤制",
    },
    "fatloss": {
        "name": "减脂",
        "kcal": (400, 550),
        "protein_min": 25,
        "notes": "控总热量与脂肪，优先烤制 + 无糖饮",
    },
    "sugar": {
        "name": "控糖 / 糖尿病",
        "kcal": (450, 650),
        "protein_min": 20,
        "carb_max": 45,
        "notes": "低碳水优先，饮料必须无糖；**不能替代医嘱**",
        "medical": True,
    },
}


def get_profile(key: str) -> dict[str, Any] | None:
    return PROFILES.get(key)


def evaluate(total: dict[str, Any], profile_key: str) -> dict[str, Any]:
    """把一份合计营养对照某人群区间，给出评价。

    返回 {profile, kcal, ok, hints[], disclaimer}
    """
    prof = PROFILES.get(profile_key)
    if not prof:
        return {"error": f"未知人群: {profile_key}"}

    kcal = total.get("energyKcal") or 0
    protein = total.get("protein") or 0
    carb = total.get("carbohydrate") or 0
    sodium = total.get("sodium") or 0

    lo, hi = prof["kcal"]
    hints: list[str] = []

    if kcal < lo:
        hints.append(f"热量偏低（{kcal} kcal，参考 {lo}–{hi}），可能吃不饱")
    elif kcal > hi:
        hints.append(f"热量偏高（{kcal} kcal，参考 {lo}–{hi}）")
    else:
        hints.append(f"热量合适（{kcal} kcal，参考 {lo}–{hi}）")

    pmin = prof.get("protein_min")
    if pmin and protein < pmin:
        hints.append(f"蛋白质不足（{protein}g，建议 ≥{pmin}g）")
    elif pmin:
        hints.append(f"蛋白质达标（{protein}g）")

    cmax = prof.get("carb_max")
    if cmax and carb > cmax:
        hints.append(f"碳水偏高（{carb}g，建议 ≤{cmax}g），可换无糖饮/去面包")
    smax = prof.get("sodium_max")
    if smax and sodium > smax:
        hints.append(f"钠偏高（{sodium}mg，儿童建议 ≤{smax}mg）")

    return {
        "profile": prof["name"],
        "kcal": kcal,
        "protein": protein,
        "ok": not any("偏高" in h or "不足" in h or "偏低" in h for h in hints),
        "hints": hints,
        "disclaimer": (
            "以上按麦当劳官方营养数据估算，不能替代医嘱，具体请遵医嘱。"
            if prof.get("medical")
            else "以上按麦当劳官方营养数据估算，实际出品有波动。"
        ),
    }


def sum_from_names(
    foods: list[dict[str, Any]],
    names: Iterable[str],
) -> tuple[dict[str, Any], list[str]]:
    """按餐品名列表累加营养，返回 (合计, 未匹配到的名字)。

    用途：套餐营养表里没有条目，必须先拆成单品名再逐个查、累加。
    未匹配的名字要如实反馈给用户，不能悄悄丢掉。
    """
    recs: list[dict[str, Any]] = []
    missing: list[str] = []
    for n in names:
        hit = lookup(foods, n)
        if hit is None:
            missing.append(n)
        else:
            recs.append(hit)
    return sum_nutrition(recs), missing
