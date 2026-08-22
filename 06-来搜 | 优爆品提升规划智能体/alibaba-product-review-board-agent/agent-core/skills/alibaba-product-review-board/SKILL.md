---
name: alibaba-product-review-board
description: "为已授权的 Alibaba.com 店铺做商品经营复盘。用户说商品复盘、低效品清理、商品质量分巡检、新品门禁、产品矩阵缺口、哪些商品该加码或优化、广告商品复盘、商品风险排查时使用。通过 Workctl 和 Accio MCP 只读采集商品效果、商品内容、质量分、风险及广告线索，生成老板可读的复盘表格和整改清单；不自动编辑、发布、删除商品或修改广告。"
---

# 商品经营复盘

把商品清单、效果、内容质量和风险证据放到同一张经营视图里，得出“加码、优化、观察、重做/下架建议”四类动作。所有结论都要能回到真实商品和数据周期。

## 先确认范围

用户未给周期或对象时，用 `ask_user` 确认：复盘周期、全店还是指定商品/类目、最关心的问题。用户只说“本周复盘”时，默认本周一至当前时间，并在表格写明口径。

## 工具与命令

Workctl 与 Accio MCP 是独立能力面。先用 `accio-mcp-cli keyword/search` 或当前工具搜索确认 schema，再使用 `accio-mcp-cli call` 或相应 Workctl 命令；不要把静态映射当成实时可用证明。

### 核心只读工具

| 目的 | Accio MCP tool | Workctl 命令 |
|---|---|---|
| 商品效果大盘 | `data_advisor_shop_product` | `workctl icbu advisor data-advisor-shop-product` |
| 商品列表与筛选 | `list_products`、`list_products_by_id`、`list_products_by_name` | `workctl icbu product list`、`list-id`、`list-name` |
| 质量分列表和明细 | `list_products_by_score`、`get_product_score_detail` | `workctl icbu product list-score`、`get-score` |
| 商品正本信息 | `product_query_information` | `workctl icbu product list-information` |
| 店铺风险 | `shop_risk_diagnosis` | `workctl icbu trade shop-risk-diagnosis` |

### 条件触发工具

| 条件 | Accio MCP tool | Workctl 命令 |
|---|---|---|
| 属性缺口或类目必填项 | `query_attribute_info`、`query_attribute_options_info` | `workctl icbu product list-attribute`、`list-attribute-options` |
| 可能涉及品牌词或侵权 | `list_risk_brand_name` | `workctl icbu product list-risk-brand-name` |
| 买家流向与补品方向 | `data_advisor_to_product` | `workctl icbu advisor data-advisor-to-product` |
| 复盘广告商品关系 | `icbu_ads_hateoas_query` | `workctl icbu ads list` |

其他工具：`list`、`read` 读取用户提供的商品表、目标和历史复盘；`write`、`bash`、`process`、`present_files` 负责生成和交付表格。

## 复盘方法

1. 先拉商品效果大盘，再补商品列表和质量分，不从单一分数直接判断经营价值。
2. 对重点商品补标题、类目、属性、图片、详情、交易信息和服务承诺。只读正本；没有用户要求时不读或修改草稿。
3. 建立四类对照：
   - 高曝光低点击：先查主图、标题、价格带和目标人群匹配。
   - 高点击低询盘：先查详情证据、MOQ、交期、认证和询盘承接。
   - 低曝光但高询盘率：判断是否值得补流量，不直接归为低效。
   - 高质量分但低效果：说明内容合规不等于市场匹配。
4. 用风险诊断做底线检查；风险线索单独列出，不扩大解释为全部经营问题。
5. 形成 P0/P1/P2/待复查动作。每条动作必须写商品 ID、证据、原因、建议、需确认字段和复查指标。

详细场景按需读取：

- `references/low_efficiency_cleanup.md`
- `references/product_score.md`
- `references/new_product_gate.md`
- `references/portfolio_review.md`
- `references/portfolio_gap.md`

## 表格交付

生成 `商品经营复盘_<周期>.xlsx`，固定包含：

| Sheet | 内容 |
|---|---|
| `经营结论` | 加码、优化、观察、重做/下架建议及最重要风险。 |
| `商品分层` | 商品 ID、标题、类目、效果、质量分、风险和分层。 |
| `问题归因` | 证据、归因、置信度和仍需核验的数据。 |
| `整改清单` | 优先级、对象、动作、负责人/确认人、复查指标和周期。 |
| `数据缺口` | 未返回、不可判断、覆盖范围和补数方式。 |

```bash
python3 scripts/build_workbook.py \
  --input review.json \
  --output outputs/商品经营复盘_<周期>.xlsx \
  --expected-sheets '经营结论,商品分层,问题归因,整改清单,数据缺口'
```

交付前回读文件，确认 5 个 sheet、无公式、无 Excel Table、无 drawing。

## 人工确认边界

- 主流程禁止商品编辑、商品发布、商品删除、批量改动、广告创建/暂停/恢复/删除/调价。
- 用户说“直接改”时，先输出拟改商品、字段、旧值、新值、影响和回滚方式；确认后转入独立执行流程。
- 下架/删除只能作为建议，不在本 Skill 内执行。
- 不编造商品 ID、效果、广告归因、负责人、库存、认证、价格或行业阈值。
