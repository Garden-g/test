# 六图 Prompt JSON 工作流

当用户要“生图 Prompt、批量 Prompt、先给 JSON 看看”时，只输出合法 JSON，不输出 Markdown、解释或图片。

## 输入处理

输入可能包含产品名称、产品描述、真实产品图、Logo、工厂/流程图、模特参考、目标买家和用户指定卖点。

- 有图片：先用 `see_image` 识别产品、可见属性、文字、品牌和风险。
- 只有关键词：用 `web_search` 理解买家关注点，但搜索结果只能形成行业假设。
- 产品身份冲突或主参考图不明确：用 `ask_user` 给出 2-4 个候选项。
- 用户未给出卖点或六图维度，且没有说“直接生成/按推荐方案”：最多用一次 `ask_user` 同时询问是否采用推荐卖点和推荐六维度、替换某个维度，或补充真实卖点。
- 未确认的认证、参数、产能、MOQ、交期、工厂和客户案例不得进入 Prompt。

## 卖点策略

先生成 5-8 个候选卖点。每个候选包含：

- `product_feature_or_mechanism`
- `buyer_problem`
- `buyer_benefit`
- `evidence`
- `visual_proof`
- `english_copy`
- `status`

只选择事实状态为 `confirmed`、`image_visible` 或 `documented` 的卖点进入最终图片。行业假设可以保留在候选中，但状态必须为 `needs_confirmation`。

最终卖点必须具体到当前产品。不得单独使用 `High Quality`、`Durable`、`High Efficiency`、`Easy to Use`、`Wide Application` 等没有产品机制、应用对象或证据支撑的表达。

## 动态六维度选择

先输出 8-12 个 `candidate_dimensions`，再根据产品特色、买家价值、事实证据、视觉表现力和素材完整度选出正好 6 个 `selected_dimensions`。用户可替换任一维度，包括指定加入 `Model or Scale`、`Application`、`Customization`、`Packaging`、`Factory Evidence` 等。

每个维度必须包含产品专属卖点和证据，不能只有通用维度名。

`image_prompts` 必须正好 6 个对象：

1. 第 1 张默认为 `High-Density Cover Hero`；只有用户明确要平台合规纯白底图时才使用 `White Background Hero`。
2. 第 2-6 张根据产品从以下角色中选择：`Core Value`、`Structure Detail`、`Application`、`Compatibility`、`Parameter Evidence`、`Performance Proof`、`Ease of Use`、`Safety or Maintenance`、`Customization`、`Packaging`、`Quality Inspection`、`Factory Evidence`、`Model or Scale`。

不得为了凑固定模板强行加入不适用的模特、工厂或参数图。六张图必须共同覆盖：

```text
Recognize → Understand value → Believe the proof → Imagine use → Complete selection → Reduce purchase risk
```

每张都是独立 `1:1` 方图，不得用六宫格、拼图、边框或 contact sheet 代替。

模特/人物维度要写明目标市场、使用场景、人物在画面中的作用、产品与人体的比例/交互方式和模特参考图状态。没有真实模特素材时，人物只能是通用商业场景中的虚构人物，不得宣称为真实客户、代言人或员工。

## 工具路由字段

### 有真实产品参考图

- 6 张产品相关输出全部计划使用 `image_edit`。
- 每个对象的 `reference_images` 都包含同一主产品图占位符。
- 工厂、质检、包装、Logo、细节或模特参考只在相应图片中追加。
- 缺失证据时替换图片角色；如果用户坚持该事实性角色，则设置 `blocked_by_missing_evidence: true`。

### 没有真实产品参考图

- 默认 `generation_route.status` 为 `needs_real_product_image`，只交付 Prompt。
- 用户明确接受概念稿后，第 1 张可计划用 `image_generate` 创建概念主参考。
- 第 2-6 张必须计划用 `image_edit`，引用已确认的第 1 张结果。
- 概念路线必须写 `publish_ready: false`，不得冒充真实商品白底图。

`task_type`、分辨率和尺寸参数不凭记忆写死，先检查当前 schema。

## Prompt 写作规则

每个英文 Prompt 写清：

- 产品身份和当前图片角色。
- 一个买家问题。
- 一条“产品特征/机制 → 买家收益 → 视觉证据”的主卖点链。
- 画面主体、场景、构图、光线、色彩和信息层级。
- 一个短标题、一条副标题和用于多个证据模块的英文短标签。
- 默认丰富度合同：标题区、2-3 个上层图标卖点、占画面 40%-55% 的产品主体、2-3 个下层应用/细节/结果卡片、3-4 个底部采购信任短项，五类中至少出现四类。
- `single standalone 1:1 square image`。
- 产品保真约束和禁止事项。

有参考图时必须加入：

```text
Keep the product exactly unchanged — preserve geometry, color, material, texture, labels, logo placement, proportions, and recognizable components.
Only change: <allowed changes>.
Do not redraw, simplify, replace, or invent any product detail.
```

通用禁止项：

```text
No grid, no collage, no contact sheet, no borders, no competitor logo, no unauthorized brand, no watermark, no phone number, no email, no URL, no QR code, no fake certification badge, no invented factory, no unreadable text, no distorted product geometry, no generic unsupported claim.
```

## 文案和证据

- Alibaba.com 六图中的可见文字使用英文。
- 每张只有一个主标题，其他文字必须是副标题或模块短标签；不使用段落文字。明确要求的纯白底主图不加营销文字。
- `OEM/ODM`、`Custom Logo`、`Custom Packaging`、`Factory Direct`、`Quality Inspection` 等属于事实性表达，只有用户资料或真实素材支持时才能使用。
- 不使用促销、价格、包邮、交付保证、平台权益、联系方式或夸张承诺。
- 工厂/流程素材缺失时，优先替换成证据更强的产品图位，不生成通用工厂图冒充用户工厂。

## 合法 JSON 结构

```json
{
  "product_name_original": "用户输入的产品名",
  "product_name_english": "确认后的英文产品名",
  "industry_type": "行业类型",
  "target_buyer": "目标买家或待确认",
  "fact_ledger": {
    "confirmed": [],
    "image_visible": [],
    "documented": [],
    "industry_hypotheses": [],
    "pending": [],
    "prohibited": []
  },
  "selling_point_strategy": {
    "user_input_status": "recommended_by_agent | provided_by_user | safe_facts_only",
    "candidate_selling_points": [
      {
        "product_feature_or_mechanism": "产品特征或机制",
        "buyer_problem": "买家问题",
        "buyer_benefit": "具体收益",
        "evidence": "事实来源",
        "visual_proof": "视觉证明方式",
        "english_copy": "短英文文案",
        "status": "confirmed | image_visible | documented | needs_confirmation"
      }
    ],
    "selected_selling_points": []
  },
  "dimension_strategy": {
    "selection_source": "recommended_by_agent | adjusted_by_user | specified_by_user",
    "candidate_dimensions": [
      {
        "dimension_name": "Product-specific dimension",
        "buyer_question": "The procurement question this dimension answers",
        "product_specific_selling_points": [],
        "evidence": [],
        "required_assets": [],
        "visual_strength": "high | medium | low",
        "blocked_by_missing_evidence": false
      }
    ],
    "selected_dimensions": ["exactly six dimension names"],
    "replaced_dimensions": []
  },
  "visual_strategy": {
    "selected_design_directions": [],
    "palette": "来自产品和品牌的配色",
    "lighting": "行业匹配的光线",
    "typography": "统一字体气质",
    "shared_visual_anchor": "整套共享视觉系统"
  },
  "generation_route": {
    "has_real_product_reference": true,
    "status": "ready_for_confirmation",
    "publish_ready": true,
    "master_reference": "<USER_PRODUCT_IMAGE>",
    "planned_calls": 6
  },
  "image_prompts": [
    {
      "id": 1,
      "selected_dimension": "Product-specific selected dimension",
      "buyer_journey_stage": "Recognize",
      "image_role": "High-Density Cover Hero",
      "buyer_question": "产品真实外观是什么？",
      "primary_selling_point": "真实完整展示",
      "buyer_benefit": "快速确认产品类型和外观",
      "visual_proof": "完整真实产品主体",
      "visible_text": [],
      "information_modules": {
        "headline_zone": {},
        "top_benefit_modules": [],
        "product_hero": {},
        "lower_evidence_cards": [],
        "procurement_confidence_strip": []
      },
      "tool": "image_edit",
      "reference_images": ["<USER_PRODUCT_IMAGE>"],
      "task_type": "resolve_from_current_schema",
      "aspect_ratio": "1:1",
      "prompt": "Complete English prompt",
      "negative_prompt": "No grid, no collage, no borders, no competitor logo, no watermark, no contact information, no QR code, no fake certification, no unsupported claim, no distorted product geometry.",
      "blocked_by_missing_evidence": false
    }
  ]
}
```

校验规则：

- JSON 外没有任何文字。
- `image_prompts` 正好 6 个对象，`id` 为 1-6。
- 第 1 张默认角色为 `High-Density Cover Hero`；用户明确要纯白底图时为 `White Background Hero`；第 2-6 张角色与产品和证据匹配。
- 除纯白底图外，每个对象的 `information_modules` 至少含 4 个非空模块类别。
- `selected_selling_points` 中没有 `needs_confirmation` 项。
- `candidate_dimensions` 有 8-12 个，`selected_dimensions` 正好 6 个，每个入选维度都有产品专属卖点和事实依据。
- 用户替换维度时，`replaced_dimensions` 记录原维度、新维度和替换理由，且总数仍为 6。
- 每个图片对象都有买家问题、主卖点、收益、视觉证据、工具、参考图、比例、Prompt 和证据阻断状态。
- 六张图回答不同问题，不只是更换背景或重复同义卖点。
- 有真实产品图时，6 个对象的 `reference_images` 都包含同一主产品参考。
- 没有真实产品图时，不得把 6 个对象全部写成 `image_generate`。
