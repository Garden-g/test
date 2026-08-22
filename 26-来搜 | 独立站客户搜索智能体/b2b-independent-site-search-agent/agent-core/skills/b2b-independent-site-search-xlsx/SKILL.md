---
name: b2b-independent-site-search-xlsx
displayName: "独立站客户搜索"
displayDescription: "用独立站搜索语法查找海外企业客户官网并生成表格名单"
description: 独立站客户搜索 XLSX 技能。Use when the user wants to find overseas independent company websites, brand sites, wholesale sites, distributor sites, retail chains, or private-label buyers by product/category, customer type, and country using Google-style search operators, then export a verified Excel workbook.
---

# 独立站客户搜索

把“产品 + 客户类型 + 国家/地区”从海外独立官网、品牌站、批发站、分销商网站和零售集团官网里整理成一份可交付的客户开发 `.xlsx`。核心原则是：先问清需求，再用公开网页证据找候选公司，过滤中国供应商和无关平台，最后只交付有来源、有空值标记、不编造的名单。

## 必填信息

如果用户没有一次性给全，先用 `ask_user` 一次性补齐，不要拆成多轮小问题：

```json
{
  "question": "请补充客户开发所需的信息。",
  "fields": [
    "要开发的产品或类目",
    "客户类型，例如 importer / wholesaler / distributor / brand / retailer",
    "目标国家或地区"
  ]
}
```

可选信息包括目标数量、排除客户、重点城市、最低公司规模、是否必须有邮箱。用户没有指定目标数量时，默认交付 50 家候选公司；最低目标是 30 家，除非公开结果确实不足。

## Tool Summary

| 步骤 | Use tool | 用途 |
| --- | --- | --- |
| 1 | `ask_user` | 补齐产品、客户类型、国家/地区，或确认多个候选方向 |
| 2 | `web_search` | 按本来源的搜索语法找公开客户线索 |
| 3 | `web_fetch` | 抓取公开页面、官网、联系页、目录页和证据页 |
| 4 | `scripts/build_customer_development_xlsx.py` | 把整理后的候选客户 JSON 渲染成安全 `.xlsx` |

`web_search` 示例入参形状：

```json
{
  "fieldName_3": {
    "payload": {
      "query": "intitle:\"pet supplies\" \"importer\" \"United States\" -site:alibaba.com -site:amazon.* -alibaba -made-in-china -1688 -aliexpress -amazon -ebay -walmart -etsy -dhgate -globalsources -facebook -instagram -linkedin -yellowpages -china supplier",
      "api": "google"
    }
  }
}
```

优先使用 `google`。如果有效结果太少，再用同一批核心搜索词切换到 `you.com` 补充。

`web_fetch` 示例：

```json
{
  "urls": [
    "https://www.example.com/",
    "https://www.example.com/about",
    "https://www.example.com/contact"
  ],
  "timeout_seconds": 30
}
```

## 执行流程

### 1. 解析目标

从用户输入或 `ask_user` 返回中提取：

- `product`：产品或类目
- `customer_type`：客户类型，例如 importer、wholesaler、distributor、brand、retailer
- `country`：目标国家、地区或城市
- `target_count`：默认 50，最低目标 30


用中文复述目标和来源，例如：“我会从海外独立官网、品牌站、批发站、分销商网站和零售集团官网里找美国宠物用品进口商，优先保留有公司主体、官网、联系方式和产品匹配证据的公司。”

### 2. 生成搜索词

围绕本来源生成 8 到 12 条搜索词。英语市场用英文；非英语市场可加当地语言客户类型词，但每批先小量验证。

核心模板：

```text
intitle:"{product}" "{customer_type}" "{country}" -site:alibaba.com -site:amazon.*
inurl:wholesale "{product}" "{country}"
inurl:distributor "{product}" "{country}"
"{product}" "{country}" "private label" "contact"
"{product}" "{country}" "our brands" "contact"
```

默认追加排除词，减少平台、中国供应商和无关页面噪声：

```text
-alibaba -made-in-china -1688 -aliexpress -amazon -ebay -walmart -etsy -dhgate -globalsources -facebook -instagram -linkedin -yellowpages -china supplier
```

除非用户明确说开发中国市场，否则默认排除中国公司、中国供应商、中国工厂和中国 B2B 平台。

### 3. 用 web_search 找候选

每条搜索结果至少提取：

| 字段 | 说明 |
| --- | --- |
| 公司名 | 标题、摘要或网页里出现的公司名称 |
| URL | 结果链接 |
| 来源类型 | 海外独立官网、品牌站、批发站、分销商网站和零售集团官网、官网、目录、社媒、新闻、行业来源、其他 |
| 国家线索 | 摘要、页面、地址、域名或标题中的国家/地区证据 |
| 产品线索 | 摘要或标题中与产品相关的词 |
| 客户类型线索 | importer / wholesaler / distributor / brand / retailer 等证据 |

候选保留：

- independent domains with company identity and target country evidence
- brand owners, wholesalers, distributors, importers, retailers, and chain stores
- sites with contact details, product catalog, or B2B trade account signals

候选剔除：

- social media, yellow pages, B2B marketplaces, marketplace stores, news articles, blog-only sites, Chinese suppliers unless requested

如果保留候选少于 30 家，先用 `you.com` 补搜，再扩展客户类型同义词、城市/地区词、来源站点和相近渠道，优先把候选池扩到 30-50 家。

### 4. 用 web_fetch 抓取证据

对每个高价值候选优先抓取：

1. independent website home page
2. About / Contact / Products / Brands pages
3. Wholesale / Distributor / Dealer / Store Locator pages
4. Terms or trade account pages when they reveal B2B role

每家公司抽取：

| 字段 | 抽取要求 |
| --- | --- |
| 公司名 | 以官网或权威页面为准 |
| 官网 | 独立 root domain；来源页不能替代官网 |
| 国家/地址 | 页面明确出现的地址、办公室或服务市场 |
| 客户类型 | 根据页面证据判断，不确定写“待确认” |
| 产品匹配点 | 页面明确展示的产品、品牌、类目、服务 |
| 联系方式 | 邮箱、电话、联系表单、社媒、地址 |
| 联系人 | 只记录公开出现的人名和职位 |
| 采购/进口线索 | import、sourcing、wholesale、distribution、dealer、brand portfolio 等公开证据 |
| 开发切入点 | 基于产品匹配和客户类型生成一句销售开发角度 |
| 风险/待确认 | 官网不可访问、信息过旧、国家不一致、只有目录页等 |
| 来源 URL | 每条关键判断必须带 URL |

缺失信息必须写 `未找到可靠公开信息`，不要编造邮箱、电话、联系人、进口记录、采购规模或公司背景。

### 5. 评分和优先级

按 100 分制评分。无法确认的项不给分，不用猜测补分：

| 维度 | 分值 |
| --- | --- |
| 产品匹配 | 0-25 |
| 客户类型匹配 | 0-20 |
| 国家/地区匹配 | 0-15 |
| 联系方式完整度 | 0-15 |
| 来源和公开证据可靠性 | 0-15 |
| 采购/进口/分销线索 | 0-10 |

优先级规则：

- `A`：80 分及以上，有来源证据、国家匹配、产品匹配、至少一种联系方式。
- `B`：60 到 79 分，方向匹配但联系方式或证据不完整。
- `C`：40 到 59 分，只能作为补充名单或待人工确认。
- `排除`：低于 40 分，或明显是平台页、同名错公司、国家不匹配、中国供应商或无关页面。

### 6. 准备脚本输入 JSON

把研究结果整理成规范 JSON，再运行脚本。所有来源都使用同一结构：

```json
{
  "input": {
    "product": "pet supplies",
    "customer_type": "importer",
    "country": "United States",
    "target_count": 50,
    "source_type": "独立站客户搜索"
  },
  "leads": [
    {
      "priority": "A",
      "score": 86,
      "company_name": "Example Pet Imports",
      "country": "United States",
      "customer_type": "importer",
      "website": "https://www.example.com/",
      "emails": ["sales@example.com"],
      "phones": ["+1 000-000-0000"],
      "address": "Los Angeles, CA, United States",
      "contacts": [
        {
          "name": "Jane Smith",
          "title": "Purchasing Manager",
          "email": "jane@example.com",
          "linkedin": "https://www.linkedin.com/in/example"
        }
      ],
      "social_links": ["https://www.linkedin.com/company/example"],
      "product_match": "官网展示 pet toys、pet grooming supplies。",
      "procurement_import_clues": "Contact 页面提到 import and wholesale distribution。",
      "development_angle": "可从 OEM pet toys 和低 MOQ 补货切入。",
      "first_email_en": "Hi Jane, I noticed your pet supplies portfolio...",
      "source_urls": ["https://www.example.com/products", "https://www.example.com/contact"],
      "confidence": "高",
      "todo": "确认采购负责人邮箱是否仍有效。"
    }
  ],
  "company_profiles": [],
  "web_evidence": [],
  "search_records": [],
  "risks": [],
  "development_advice": []
}
```

运行：

```bash
python3 "$SKILL_ROOT/scripts/build_customer_development_xlsx.py"   --input "$WORKSPACE_ROOT/customer_development.json"   --output "$WORKSPACE_ROOT/customer_development.xlsx"
```

路径约定：

```bash
SKILL_ROOT="$SKILL_INSTALL_PATH"
WORKSPACE_ROOT="$PWD"
```

`SKILL_INSTALL_PATH` 使用读取 `$b2b-independent-site-search-xlsx` 时返回的 `install_path`；不要硬编码开发机路径。

### 7. 交付要求

交付前必须确认脚本成功完成：

- 生成 `.xlsx`
- 生成同名 `.log`
- LibreOffice headless 重存成功
- `unzip -t` 通过
- `openpyxl.load_workbook()` 通过
- 包内无非预期 `xl/tables/`、`xl/drawings/`、`tableParts`、drawing/table relationships

最终回复用户时说明文件路径、候选客户数量、A/B/C 优先级数量、关键缺口，以及公开来源证据边界。

## 来源边界

独立站搜索以公司官网为主。目录页、社媒和平台结果只能作为辅助发现，不进入主名单，除非能找到对应独立官网。
