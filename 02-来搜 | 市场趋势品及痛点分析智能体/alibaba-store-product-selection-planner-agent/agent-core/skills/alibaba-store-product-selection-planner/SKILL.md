---
name: alibaba-store-product-selection-planner
description: "为已授权的 Alibaba.com 店铺做选品定位和商品结构规划。用户说店铺选品、卖什么产品、类目定位、机会品、产品矩阵、国家市场匹配、根据店铺数据选新品、该扩哪条产品线时使用。必须先用 ask_user 获取经营目标与供应约束，再通过 Workctl 和 Accio MCP 只读采集店铺及行业证据，形成候选赛道后第二次用 ask_user 让用户选择，最后生成可追溯的选品定位表格；不自动创建、编辑、发布或删除商品。"
---

# 店铺选品定位

把“有什么能卖”收敛成“这家店凭什么卖、先卖给谁、用哪组产品验证”。本 Skill 必须经历两次用户确认，不能只看热度榜自动决定选品。

## 必须先问，再读数据

第一次调用 `ask_user`，集中询问最多 3 组问题：

1. 经营目标：拉新、提升询盘、提高客单、补齐产品矩阵、进入新国家，哪一个优先。
2. 供应边界：可生产类目、MOQ、目标价带、交期、认证、定制能力、毛利底线、禁做产品。
3. 目标范围：已有店铺还是新店；重点国家、客户类型、周期和希望输出多少个方向。

即使用户说“你直接选”，也要通过 `ask_user` 至少确认供应边界和明确禁区。没有这些约束，市场热度不能转成可执行选品。

## 工具与证据层

Workctl 命令和 Accio MCP tool 是两套独立能力面。先确认当前可用 schema，再调用；不能因为某个 Workctl 命令存在，就假定同名 MCP tool 一定可用。

### 工具发现与文件

- `ask_user`：第一次确认经营与供应约束；第二次确认候选赛道。
- `list`、`read`：读取用户提供的产品目录、销售表格、认证清单、历史报告和品牌资料。
- `accio-mcp-cli keyword`：按业务词找可能工具。
- `accio-mcp-cli search`：查看准确 tool 名、参数和只读属性。
- `accio-mcp-cli call`：只在 schema 已确认后调用只读 tool。
- `write`、`bash`、`process`、`present_files`：准备 JSON、运行表格脚本、检查结果并交付文件。

### 店铺现状：优先采集

| 业务问题 | Accio MCP tool | Workctl 命令 |
|---|---|---|
| 店铺有哪些经营类目 | `query_user_category` | `workctl icbu product list-user-category` |
| 店铺有哪些商品 | `list_products` | `workctl icbu product list` |
| 店铺整体经营概况 | `data_advisor_shop_summary` | `workctl icbu advisor data-advisor-shop-summary` |
| 商品表现与结构 | `data_advisor_shop_product` | `workctl icbu advisor data-advisor-shop-product` |
| 客户画像 | `data_advisor_shop_customer_profile` | `workctl icbu advisor data-advisor-shop-customer-profile` |
| 国家与区域 | `data_advisor_shop_region` | `workctl icbu advisor data-advisor-shop-region` |
| 渠道与流量 | `data_advisor_shop_channel`、`data_advisor_shop_flow`、`data_advisor_shop_flow_profile` | `workctl icbu advisor data-advisor-shop-channel`、`data-advisor-shop-flow`、`data-advisor-shop-flow-profile` |
| 买家还流向哪些商品 | `data_advisor_to_product` | `workctl icbu advisor data-advisor-to-product` |

### 行业机会：按需采集

| 业务问题 | Accio MCP tool | Workctl 命令 |
|---|---|---|
| 类目识别与预测 | `data_advisor_category_infer`、`data_advisor_category_prediction` | `workctl icbu product data-advisor-category-infer`、`data-advisor-category-prediction` |
| 市场规模与趋势 | `data_advisor_industry_market_detail`、`data_advisor_industry_market_trend` | `workctl icbu product data-advisor-industry-market-detail`、`data-advisor-industry-market-trend` |
| 类目与国家排名 | `data_advisor_industry_cate_rank`、`data_advisor_industry_country_rank` | `workctl icbu product data-advisor-industry-cate-rank`、`data-advisor-industry-country-rank` |
| 买家渠道与画像 | `data_advisor_industry_buyer_channel`、`data_advisor_industry_buyer_profile`、`data_advisor_industry_crowd_insight` | `workctl icbu product data-advisor-industry-buyer-channel`、`data-advisor-industry-buyer-profile`、`data-advisor-industry-crowd-insight` |
| 机会发现与选品建议 | `data_advisor_opportunity_discovery`、`data_advisor_product_selection` | `workctl icbu product data-advisor-opportunity-discovery`、`data-advisor-product-selection` |

只调用回答当前问题所需的最小工具集。分页、周期、类目 ID 和国家枚举均以实时 schema 为准。权限不足、数据为空或只覆盖部分周期时，写明“未返回”“不可判断”或“仅覆盖已获取范围”。

## 分析步骤

1. 把第一次 `ask_user` 的答案整理成硬约束、偏好、禁区和待确认项。
2. 读取店铺类目、商品结构、商品效果、客户画像和国家流量，判断店铺已有优势与明显缺口。
3. 按需补行业趋势、国家、买家和机会证据；不把平台建议直接当最终结论。
4. 形成 3-5 个候选赛道。每个赛道至少说明：目标客户、使用场景、产品簇、店铺证据、市场证据、供应匹配、主要风险、最小验证动作。
5. 使用统一评分框架：供应匹配 25、店铺证据 25、市场需求 25、竞争与差异化 15、交付及合规风险 10。权重是规划模板，可按用户目标调整，不是行业事实。
6. 第二次调用 `ask_user`，展示候选赛道并让用户选择主赛道、备选赛道或要求重算。没有用户选择，不进入最终产品矩阵。
7. 对选中赛道拆出引流品、主推品、利润品、形象品和试验品，给出验证周期、停止条件和所需证据。

## 第二次 Ask User 模板

向用户展示最多 3 个首选方向，每个方向用一句业务语言说明收益与代价。建议选项格式：

- `方向 A（推荐）`：最贴近现有店铺证据，验证成本低，但增长上限中等。
- `方向 B`：市场机会更大，但需要补认证或供应能力。
- `方向 C`：差异化明显，但当前店铺证据较弱，适合作为小样测试。

如果用户选“重算”，必须问清不满意的是产品、国家、价带、风险还是供应约束。

## 表格交付

固定生成 `店铺选品定位_<YYYY-MM-DD>.xlsx`，包含：

| Sheet | 内容 |
|---|---|
| `经营结论` | 主赛道、备选赛道、不建议方向、关键理由和本期目标。 |
| `店铺证据` | 类目、商品、客户、国家、渠道和流量证据及数据范围。 |
| `候选赛道` | 3-5 个方向的评分、证据、风险和用户选择。 |
| `产品矩阵` | 引流品、主推品、利润品、形象品、试验品及优先级。 |
| `验证计划` | 最小测试、负责人、周期、成功指标、停止条件。 |
| `数据缺口` | 未返回、不可判断、仅覆盖范围和补数方式。 |

准备规范化 JSON 后运行：

```bash
python3 scripts/build_workbook.py \
  --input selection.json \
  --output outputs/店铺选品定位_<YYYY-MM-DD>.xlsx \
  --expected-sheets '经营结论,店铺证据,候选赛道,产品矩阵,验证计划,数据缺口'
```

必须回读生成文件并确认 6 个 sheet、无公式、无 Excel Table、无 drawing 后再用 `present_files` 交付。

## 边界

- 主流程只读，不调用创建商品、编辑商品、发布商品、删除商品、改广告或改页面的工具。
- 不编造销量、询盘、毛利、库存、认证、产能、负责人或行业均值。
- 不因单一热度、单一排名或单一商品分数推荐赛道。
- 用户确认选品方向不等于确认发布商品；后续发品必须转入独立发品流程并再次确认。
