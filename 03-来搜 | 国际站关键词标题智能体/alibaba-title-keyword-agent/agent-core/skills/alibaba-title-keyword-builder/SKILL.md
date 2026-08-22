---
name: alibaba-title-keyword-builder
description: "国际站关键词调研与批量标题生成。用于根据产品资料、竞品链接、亚马逊/Google/阿里国际站搜索结果、阿里关键词指数、已有商品 ID、关键词表或用户给出的属性词，拆解核心词、属性词、场景词、营销词和多语言同义词，清洗 C 端词、侵权词和不相关属性后，生成适合 Alibaba.com 国际站批量上传或商品标题优化的英文标题表。当用户提到“生成国际站标题”“批量标题”“关键词标题”“阿里标题”“标题词库”“产品标题流程”“从竞品拆词”“关键词指数”“弹力帐篷标题参考”“窗帘标题”“批量上传标题”等场景时使用。"
---

# 国际站关键词标题生成

把产品资料、竞品标题和平台关键词数据整理成可执行的标题词库，并生成一批适合国际站批量上传的英文产品标题。

默认只输出标题表和风险提示。只有用户明确要求写入已有商品，并二次确认具体商品 ID 与标题内容后，才调用写入工具。

## 核心原则

- 先问清产品事实，再做关键词扩展；不要为了凑词编造材质、克重、尺寸、工艺、认证、适用场景或产能。
- 标题必须围绕真实产品，不要把和主图无关的属性写进去。例如用户排除“提花、压花、便携”，就不能再把这些词塞进标题。
- 词库先分层：核心词、属性词、场景词、营销词、多语言/同义词、排除词。
- 优先保留 B2B 采购意图词，清理 C 端个人购买、家装消费、品牌侵权、平台名、公司名和竞品品牌词。
- 核心关键词必须进入每条标题；属性词优先级高于场景词，场景词优先级高于营销词。
- 标题里同一个英文单词重复不得超过 3 次；超过 128 个字符必须重写。
- 输出必须能让用户直接复制到批量上传表或商品编辑流程中。

## 工具地图

| 阶段 | 工具 | 用途 |
| --- | --- | --- |
| 已有国际站商品读取 | `list_products` / `list_products_by_id` / `list_products_by_name` | 读取用户自己的商品标题、类目、属性、图片、卖点和 leafId |
| 外部竞品链接抽取 | `web_fetch` | 抓取 Amazon、独立站、1688、速卖通等外部页面标题和卖点 |
| 热卖竞品参考 | `global_hot_selling_products` | 按关键词在 Amazon 等平台找热卖商品，补充标题常用表达 |
| 品牌广告候选词 | `searchKeywordList` | 仅用于品牌广告可售关键词及其返回指标；不能冒充全站自然搜索关键词指数 |
| 类目和属性读取 | `data_advisor_category_infer` / `data_advisor_category_prediction` + `query_attribute_info` / `query_attribute_options_info` | 辅助判断类目，按 `propertyType` 读取属性定义，并按属性 ID 查询系统选项 |
| 风控品牌词 | `list_risk_brand_name` | 查询类目品牌风控词，避免标题包含高风险品牌 |
| 商品标题写入 | `batch_edit_product` | 仅在用户明确确认后，把标题写入指定国际站商品 |

工具调用入参直接传 JSON 对象，不要包额外的 `--json` 字符串。

## 工作流

### 1. 先收集产品事实和排除项

如果用户只给一个产品名或竞品链接，先问 3-6 个关键问题，不要直接生成标题：

- 产品是什么，核心英文词是否已有。
- 材质、成分、克重、厚度、尺寸、颜色、结构、工艺、包装或可定制项。
- 真实用途和目标客户，例如 wedding event、hotel、restaurant、factory、outdoor event。
- 明确排除的属性词，例如提花、压花、便携、家装、儿童房、个人购买等。
- 需要生成多少条标题，是否要小语种同义词。
- 是否只要预览，还是最终要写入已有商品 ID。

如果用户已经给出完整属性表，可直接进入第 2 步。

### 2. 建立关键词来源

按用户提供的信息选择来源，不需要每次都全部调用：

1. 用户给国际站商品 ID：调用 `list_products` 或 `list_products_by_id` 读取商品标题、类目、属性和 leafId。
2. 用户给外部竞品 URL：调用 `web_fetch` 抽取标题、卖点、规格和品牌词；抽取失败时让用户粘贴页面文字，不要猜。
3. 用户要求参考 Amazon 热卖：调用 `global_hot_selling_products`，例如：

```json
{"query":"blackout curtains for hotel wholesale","platform":"amazon","region":"US","sorting_rule":"sales","type":"hot_selling"}
```

4. 只有用户明确要求品牌广告候选词/可售词时，才用 2-4 个中心词调用 `searchKeywordList`。它不是通用自然搜索词库；用户要自然搜索关键词研究时，使用产品事实、公开搜索和已验证的平台数据，并明确来源。品牌广告默认先查 PC 渠道并按返回的曝光字段降序：

```json
{
  "query": {
    "productId": 110102001,
    "keywordList": [
      {"keyword": "blackout curtain", "channel": "PC"},
      {"keyword": "blackout curtains", "channel": "PC"},
      {"keyword": "black out curtains", "channel": "PC"}
    ],
    "requestOrderProperty": {"orderField": "yearImps", "orderType": "desc"},
    "requestPage": {"pageIndex": 1, "pageSize": 100}
  }
}
```

`searchKeywordList.query.productId` 是品牌广告产品类型。默认用 `110102001`；用户明确要求顶展/另一个产品类型时再改为对应枚举。最终表必须把这批数据标记为“品牌广告候选词”，不能写成“Alibaba.com 全站关键词指数”。

### 3. 拆成标题词库

生成标题前，先把词整理成一张词库表：

| 分类 | 内容 |
| --- | --- |
| 核心词 | 产品本体词和近义词，如 `stretch tent`、`bedouin stretch tent`、`blackout curtain` |
| 多语言/同义词 | 如 `cortina`、`gordijn`、`Vorhang`，只在用户要求或该市场明显相关时使用 |
| 属性词 | 材质、功能、结构、颜色、尺寸、克重、厚度、涂层、工艺、套装数量 |
| 场景词 | wedding、event、party、hotel、restaurant、garden、beach、commercial event |
| 营销词 | custom、wholesale、factory price、supplier、manufacturer、high quality |
| 排除词 | 品牌名、公司名、平台名、C 端购买词、不相关属性、用户明确排除词 |

详细标题公式和清洗规则见 [title-rules.md](references/title-rules.md)。在生成最终批量标题前必须读取该文件。

### 4. 清洗关键词

清洗时给出“删除原因”，方便用户判断是否要恢复某些词：

- 品牌/公司/平台词：Amazon、店铺名、竞品品牌、他人商标。
- C 端词：buy、bedroom decor、for kids room、home decoration、DIY、personal use 等，除非用户明确要覆盖零售流量。
- 不相关属性：主图或真实产品不具备的工艺、材质、结构、尺寸、便携性。
- 虚假强词：best、top、No.1、perfect、guaranteed、original 等绝对化表达。
- 低质量词：拼写错误、无意义年份、重复堆叠、只提升噪音不提升搜索意图的词。

### 5. 生成标题

按“核心词数量”选择策略：

- 核心词多且意思接近：同一标题可放 1-2 个核心词变体，如 `blackout curtain` + `cortina`。
- 核心词少：先放真实属性词，再放场景词，最后补营销词。
- 标题中的介词放在核心词后面，并靠后连接应用场景，例如 `Stretch Tent for Wedding Event Party`。
- 每条标题都要能拆回词库表，不能出现来源不明的词。

输出至少包含这些列：

| 列名 | 说明 |
| --- | --- |
| `title_id` | 标题编号 |
| `product_fit` | 适用产品/属性组合 |
| `title` | 英文标题 |
| `char_count` | 字符数 |
| `core_keywords` | 使用的核心词 |
| `attribute_terms` | 使用的属性词 |
| `scenario_terms` | 使用的场景词 |
| `marketing_terms` | 使用的营销词 |
| `source_terms` | 主要来源词 |
| `risk_notes` | 重复词、侵权、属性不确定等提示 |

### 6. 校验并展示结果

生成标题后先自检：

- 字符数不超过 128。
- 同一英文单词重复不超过 3 次。
- 标题没有品牌名、公司名、平台名和用户排除词。
- 标题里每个属性都能对应用户资料、图片、商品 ID 或关键词来源。
- 标题之间不要只是调换顺序；核心词、属性词和场景词组合要有差异。

如果本地环境可运行脚本，可用辅助校验：

```bash
python scripts/check_titles.py --input titles.txt --max-chars 128
```

脚本只能发现机械问题；最终仍要按产品真实性和平台规则人工复核。

### 7. 可选写入商品

默认不要写入。用户明确说“确认写入这些商品标题”后：

1. 展示 `productId -> title` 对照表。
2. 提醒写入会覆盖商品原标题。
3. 等用户再次确认。
4. 调用 `batch_edit_product`，只传已确认商品的 `productId` 和 `productTitle`：

```json
{
  "editList": [
    {"productId": 1600000000000, "productTitle": "Custom Waterproof Stretch Tent for Wedding Event Party Outdoor Commercial Use"}
  ]
}
```

如果用户只要“生成标题表用于批量上传”，不要调用写入工具。
