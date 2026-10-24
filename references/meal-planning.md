# 省钱 / 营养双轨策略打法

> ⚠️ 营养部分是按**麦当劳官方营养数据**做的参考搭配，**不是医疗或营养处方**。
> 涉及疾病（糖尿病等）必须提示遵医嘱。所有分型区间属**通行实践值，非官方规定**。

---

## 一、极致省钱模式

### 1.1 省钱的三层来源

省钱不是"找最便宜的"，是**三层叠加**：

| 层 | 来源 | 工具 | 常见漏点 |
|---|---|---|---|
| L1 单品价 | 门店划线价 | `query-meals` 的 `originalPrice` vs `currentPrice` | 只看 `currentPrice`，忽略 `discountType` 标明的额外优惠 |
| L2 券 | 麦麦省 / 卡包 / 门店券 | `available-coupons`、`query-my-coupons`、`query-store-coupons` | **没领的券等于没有** |
| L3 组合 | 满减、第二份半价、随心配1+1 | `calculate-price` 试算 | 不试算直接推荐，省的钱是拍脑袋的 |
| L4 积分 | 麦享会积分兑券 | `query-my-account` + `mall-points-products` | **积分会过期，不用就是浪费** |

**最大的钱漏在 L2 和 L4**：
- 券包里躺着没领的券
- 积分躺在账户里等到过期（实测某账号已过期 1341.9 分）

### 1.2 标准流程

```
① query-nearby-stores(beType=1, searchType=1)
   └─ 拿到 storeCode
② query-meals(storeCode, orderType=1, beType=1)
   └─ 扫 meals{}，筛出：
      · currentPrice 最低的一批
      · discountType 非 null 的（有额外优惠）
      · tags 含"超值""随心配""限时特惠"的
③ available-coupons()
   └─ 有"未领取" → 提示用户，征得同意后 auto-bind-coupons()
④ query-my-coupons() + query-store-coupons(storeCode, 1, 1)
   └─ 汇总可用券清单
⑤ query-my-account() + mall-points-products(catRuleIds="1>4")
   └─ 看积分能不能换券，能换就问用户
⑥ 组 2–3 套方案 → 每套 calculate-price 核价
   └─ 带券和不带券各算一次，对比出真省额
⑦ 输出：实付 + 帮你省了多少
```

### 1.3 组合思路

**随心配 1+1**：麦当劳招牌超值项目，蓝区+粉区各选一，超百种组合。**省钱首选**。

**大堡口福**：三件套超值套餐，扎实管饱。

**"第二份半价"**：`tags` 里有标记的。**必须 `calculate-price` 传 `quantity: 2` 验证**，不要自己算半价。

**"随单购"**：`query-meals` 返回的 `isCanWithOrder` / `withOrder`。买正价品时顺手加麦金卡/早餐卡能再省。`withOrder` 对象要原样带进 `calculate-price` 和 `create-order`。

**券的叠加**：部分券不能叠加。**不要假设能叠**，分别试算：
- 方案 a：商品 + 券 A
- 方案 b：商品 + 券 B
- 方案 c：商品 + 券 A + 券 B（如果工具接受）

工具报错或优惠额没变，说明不可叠。

### 1.4 常见坑

| 坑 | 说明 |
|---|---|
| 金额单位 | `calculate-price` 返回**分**，`create-order` 的 `orderDetail` 返回**元字符串**。混用必错 |
| 到店传 beCode | `orderType=1` 时传 `beCode` 会报错 |
| 券的有效期 | `tradeDateTime` 是范围字符串，注意是否已过期 |
| 券的适用范围 | `products[]` 限定了适用商品，用在别的商品上无效 |
| 限流 | 别在循环里狂调 `calculate-price`，一次可传多个 `items` |
| 门店差异 | 不同门店菜单和价格不同，**不能拿 A 店价格说 B 店** |

---

## 二、营养模式

### 2.1 先问清是谁吃（关键）

**不同人群目标完全不同，这一步不能省。**

| 人群 key | 名称 | 热量区间(kcal) | 蛋白下限 | 额外约束 |
|---|---|---|---|---|
| `adult` | 成人日常 | 500–700 | 20g | — |
| `kid` | 儿童(3–12) | 300–500 | 12g | 钠 ≤800mg |
| `fitness` | 健身增肌 | 600–900 | 30g | — |
| `fatloss` | 减脂 | 400–550 | 25g | — |
| `sugar` | 控糖/糖尿病 | 450–650 | 20g | 碳水 ≤45g，**必须带医嘱提示** |

> 区间为**通行实践参考值**，非官方规定。依据：中国居民膳食指南对成人一餐的常见建议
> （约 1/3 日需）+ 常见减脂/增肌实践区间。

**问法**（一句话）：

> 是给你自己吃，还是给小朋友？有没有要特别注意的（比如健身、控糖）？

**用户提疾病时**，输出必须加：

> 以上只是按官方营养数据做的参考搭配，**不能替代医嘱**，具体请遵医嘱。

### 2.2 营养数据怎么拿

```
list-nutrition-foods()   ← 无入参，返回全部营养表（实测 160 条）
```

**返回值包了三层**（`result.content[0].text` 是 Markdown 说明，真数据在
`## Original Response` 之后的 JSON 里，其 `data` 才是 TOON）。用 `scripts/nutrition.py`：

```python
from nutrition import (load_from_mcp_result, lookup, lookup_or_ask,
                       sum_from_names, evaluate, format_summary)

foods = load_from_mcp_result(raw)

# 单品
hit = lookup(foods, "板烧鸡腿堡")

# 规格不明 → 给候选让用户选
hit, cands = lookup_or_ask(foods, "玉米杯")

# 套餐：拆成单品名，逐个查再累加
total, missing = sum_from_names(foods, ["板烧鸡腿堡", "中薯条", "可乐中杯"])

# 按人群评估
ev = evaluate(total, "kid")     # kid / fitness / fatloss / sugar / adult
```

### 2.3 套餐必须拆开算（重要）

**实测确认：营养表里没有套餐条目，只有单品。**

```
① query-meal-detail(storeCode, orderType, beType, code)
   → 从 rounds[].choices[] 看这个套餐由哪些单品组成
   → 找被选中的（quantity=1 或 isDefault=1）
② 每个单品名丢进营养表查
③ sum_from_names() 累加
```

**例**："精选单人餐三件套" = 板烧鸡腿堡(391) + 中薯条(289) + 中可(147) ≈ 827 kcal

**对不上就如实说**："这个套餐官方没给整份营养值，我按里面单品加总，可能略有出入"。

### 2.4 匹配铁律（踩过坑）

1. **规格不明就问。** "玉米杯"官方只有"大杯/小杯"→ 给候选让用户选，绝不默认。
2. **修饰词不能串味。** "零度/无糖可乐" 0 kcal vs "可乐" 147 kcal。
   （实测教训：早期把"零度可口可乐中杯"错配成"可乐中杯"，健康建议完全失效。）
3. **查不到就说查不到。** 不拿近似品顶替。

### 2.5 平替（用真实数据说话）

| 换成 | 收益 | 数据来源 |
|---|---|---|
| 含糖可乐 → 无糖可乐 | 省约 100–150 kcal | 两条记录相减 |
| 薯条 → 玉米杯 | 省约 150–200 kcal，脂肪大降 | 两条记录相减 |
| 炸鸡腿堡 → 板烧鸡腿堡 | 脂肪明显降低 | 两条记录相减 |
| 去酱 / 去芝士 | 省 50–100 kcal | ⚠️ **官方无独立数据**，只能说"通常" |
| 双层 → 单层 | 省约一份肉饼 | 有对应记录就相减，没有就说"约" |

**去酱怎么落地**：`query-meal-detail` 的 `modification.items[].values[]` 找酱料项，
记下 `code` 和 `unselectedKey`，下单传：

```json
{ "code": "120512", "quantity": 0, "key": "0-0" }
```

`quantity=0` + `unselectedKey` = 去掉。**先 `calculate-price` 验证**，再下单。

### 2.6 输出模板

```
方案｜减脂向（成人）
  板烧鸡腿堡（去酱）       391 kcal ｜ 蛋白 23g
  大杯玉米杯                87 kcal ｜ 蛋白  4g
  无糖可乐中杯               0 kcal
  ──────────────────────────────────
  合计 ≈ 478 kcal ｜ 蛋白质 ≈ 27g
  · 热量合适（478 kcal，参考 400–550）
  · 蛋白质达标（27g）

热量蛋白基于麦当劳官方营养数据，实际出品有波动。
去酱的实际减量官方未提供，未计入。
```

**必须带免责**。

---

## 三、麦门文学写作要点

见 `references/mcd-ad-slogans.md`（含广告语库 + 敏感词红线 + 正反示例）。

**核心速记**：
- ≤100 字，结合真实餐品 + 当下情绪
- 能融广告语就融，不能融不硬凑；一次最多一句
- **红线**：不碰政治/宗教/民族/地域/疾病/性别/未成年人
- 判定标准：读完"会心一笑"而非"心里一沉"

