#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
隐私脱敏工具。

用于在对话输出、生成文案、写文件之前，把敏感信息处理掉：
  - 手机号（含带分隔符写法）   -> 1XX****XXXX
  - 订单号                     -> 只保留后 6 位
  - 详细地址 / 门牌号          -> 只保留行政区
  - 身份证 / 邮箱 / 微信号      -> 部分打码
  - Token（Bearer 与裸值）      -> 全部替换为 ***

工具返回的数据本身已部分脱敏，本模块是"最后一道防线"，
避免漏网的原始值进入对外内容。

用法：
    from redact import redact_text, redact_dict

    safe = redact_text(user_facing_text)                  # 给用户看
    safe = redact_dict(data, for_storage=True)            # 写文件/记日志
"""

from __future__ import annotations

import re
from typing import Any

# 中国大陆手机号：1 开头，第二位 3-9，共 11 位
PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")

# 带分隔符的手机号：1XX-XXXX-XXXX / 1XX XXXX XXXX / 1XX.XXXX.XXXX
# 允许 3-4-4 或 3-3-4-4 等常见分隔写法，分隔符为 - / 空格 / .
PHONE_SEP_RE = re.compile(
    r"(?<!\d)(1[3-9]\d)[\-\s.]?(\d{3,4})[\-\s.]?(\d{4})(?!\d)"
)

# 已脱敏的手机号（1XX****XXXX），避免二次处理
PHONE_MASKED_RE = re.compile(r"(?<!\d)(1[3-9]\d)\*{2,}(\d{4})(?!\d)")

# 裸 Token：token=xxx / token: xxx / accessToken=xxx
# 麦当劳 Token 是长随机串，取 12 位以上避免误伤普通短词
BARE_TOKEN_RE = re.compile(
    r"(?i)\b(token|access_?token|api_?key|secret|apikey)\b\s*[:=]\s*[\"']?([A-Za-z0-9\-._~+/]{12,})[\"']?"
)

# 微信号 / 昵称类字段值（出现在文本里的显式声明）
WECHAT_RE = re.compile(
    r"(微信号|微信|wechat|wxid|昵称|nickname)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_\-]{5,19})"
)

# 订单号：麦当劳订单为 20+ 位纯数字，或 ECS 开头的商城订单
ORDER_RE = re.compile(r"(?<![A-Za-z0-9])((?:ECS)?\d{16,})(?![0-9])")

# Bearer token
TOKEN_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9\-._~+/]{8,})", re.IGNORECASE)

# 门牌号：X号/栋/单元/室/楼 结尾的片段
# 两种形态：
#   a) 带汉字前缀  "XX小区3号楼2单元XXX室"
#   b) 纯数字开头  "X楼XXX室" / "X单元XXX室" / "XXX号"
DOOR_RE = re.compile(
    r"(?:"
    r"[\u4e00-\u9fa5A-Za-z0-9\-]{1,10}?(?:号楼|栋|单元|室|层|楼)\s*\d*[\u4e00-\u9fa5A-Za-z0-9\-]{0,8}"
    r"|"
    r"(?<![\d\u4e00-\u9fa5])\d{1,4}\s*(?:号楼|栋|单元|室|层|楼|号)\s*\d{0,4}\s*(?:室|号|层|楼)?"
    r")"
)

# 身份证
IDCARD_RE = re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3})([\dXx])(?!\d)")

# 邮箱
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+\-]{1,3})[A-Za-z0-9._%+\-]*(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")


def mask_phone(phone: str) -> str:
    """1XX****XXXX；已脱敏的原样返回。"""
    if not phone:
        return ""
    s = str(phone).strip()
    if PHONE_MASKED_RE.fullmatch(s):
        return s
    return PHONE_RE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", s)


def mask_order_id(order_id: str, *, keep: int = 6) -> str:
    """长订单号只保留后 keep 位：...XXXXXX"""
    if not order_id:
        return ""
    s = str(order_id).strip()
    if len(s) <= keep:
        return s
    return f"...{s[-keep:]}"


def mask_address(address: str, *, keep_head: int = 3) -> str:
    """地址只保留前 keep 个字，其余打码。

    长地址（含行政区）-> 前 3 字 + ***
    短地址（纯门牌）  -> ***
    """
    if not address:
        return ""
    s = str(address).strip()
    # 短地址（仅门牌无行政区）整体打码
    if len(s) <= keep_head * 2:
        return "***"
    return s[:keep_head] + "***"


def mask_token(token: str) -> str:
    """Token 永不回显实际值。"""
    if not token:
        return ""
    return "***"


def mask_pay_url(url: str) -> str:
    """付款链接打码：保留域名便于用户识别，抹掉带签名的查询串。

    https://<域名>/pay?<签名参数> -> https://<域名>/pay?***
    """
    if not url:
        return ""
    s = str(url).strip()
    if "?" not in s:
        return s
    base, _, _query = s.partition("?")
    return f"{base}?***"


def redact_text(text: str, *, mask_addr: bool = True) -> str:
    """对一段文本做全量脱敏。"""
    if not text:
        return ""
    s = str(text)

    # Token 优先（避免被其他规则破坏结构）
    s = TOKEN_RE.sub(lambda m: m.group(1) + "***", s)
    # 裸 Token：token=xxx（无 Bearer 前缀）
    s = BARE_TOKEN_RE.sub(lambda m: f"{m.group(1)}=***", s)

    # 手机号：先处理已脱敏的（幂等），再处理带分隔符的，最后处理纯数字
    s = PHONE_MASKED_RE.sub(lambda m: m.group(0), s)  # 占位，保证不被 SEP 规则误伤
    s = PHONE_SEP_RE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", s)
    s = PHONE_RE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", s)

    # 微信号 / 昵称
    s = WECHAT_RE.sub(lambda m: f"{m.group(1)}:***", s)

    # 身份证
    s = IDCARD_RE.sub(lambda m: f"{m.group(1)}********{m.group(3)}{m.group(4)}", s)

    # 邮箱
    s = EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", s)

    # 订单号（放在手机号之后，避免误伤已脱敏的手机号）
    s = ORDER_RE.sub(lambda m: mask_order_id(m.group(1)), s)

    # 门牌号
    if mask_addr:
        s = DOOR_RE.sub("***", s)

    return s


# 字段名 -> 脱敏函数
_FIELD_RULES: dict[str, Any] = {
    "phone": mask_phone,
    "mobile": mask_phone,
    "mobilePhone": mask_phone,
    "contactPhone": mask_phone,
    "telephone": mask_phone,
    "tel": mask_phone,
    "receiverPhone": mask_phone,
    "riderMobilePhone": mask_phone,
    "orderId": mask_order_id,
    "orderNo": mask_order_id,
    "tradeNo": mask_order_id,
    "address": mask_address,
    "fullAddress": mask_address,
    "addressDetail": mask_address,
    "detailAddress": mask_address,
    "deliveryAddress": mask_address,
    "receiverAddress": mask_address,
    "storeAddress": mask_address,
    "contactName": lambda v: "***",
    "receiverName": lambda v: "***",
    "customerNickname": lambda v: "***",
    "nickname": lambda v: "***",
    "nickName": lambda v: "***",
    "wechat": lambda v: "***",
    "wechatId": lambda v: "***",
    "wxId": lambda v: "***",
    "token": mask_token,
    "accessToken": mask_token,
    "access_token": mask_token,
    "authorization": mask_token,
    "Authorization": mask_token,
    "apiKey": mask_token,
    "secret": mask_token,
}

# 需要整体跳过（不脱敏也不展示）的字段
_DROP_FIELDS = {
    "lockerQrCode",
    "couponQrCode",
    "qrCode",
}

# 付款链接：给用户本人时必须保留（他要付款），
# 但**写文件 / 记日志 / 转发**时按 mask_pay_url 打码，避免被他人代付。
_PAY_URL_FIELDS = {"payH5Url", "payUrl", "h5Url", "paymentUrl"}


def redact_dict(obj: Any, *, _depth: int = 0, for_storage: bool = False) -> Any:
    """递归脱敏字典/列表中的敏感字段。

    不修改原对象，返回新对象。

    参数：
        for_storage=False（默认）：面向用户展示。付款链接**保留**，用户要点它付款。
        for_storage=True：写入文件 / 记日志 / 对外转发。付款链接**打码**，
                          避免链接被他人拿到后代付。
    """
    if _depth > 12:
        return obj

    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _DROP_FIELDS:
                out[k] = "***"
                continue
            if k in _PAY_URL_FIELDS and isinstance(v, str):
                out[k] = mask_pay_url(v) if for_storage else v
                continue
            rule = _FIELD_RULES.get(k)
            if rule is not None and isinstance(v, str):
                out[k] = rule(v)
            elif isinstance(v, str) and k.lower() in {"remark", "note"}:
                out[k] = redact_text(v)
            else:
                out[k] = redact_dict(v, _depth=_depth + 1, for_storage=for_storage)
        return out

    if isinstance(obj, list):
        return [redact_dict(i, _depth=_depth + 1, for_storage=for_storage) for i in obj]

    if isinstance(obj, str):
        return redact_text(obj)

    return obj
