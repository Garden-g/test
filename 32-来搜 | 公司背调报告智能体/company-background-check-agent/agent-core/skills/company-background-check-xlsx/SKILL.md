---
name: company-background-check-xlsx
displayName: "公司背调报告"
displayDescription: "按国家和公司名确认官网并生成可核验的公司背调表格"
description: 国家 + 公司名背调报告 XLSX 技能。用户只给国家和公司名时，用 Accio 的 web_search、web_fetch、ask_user，以及 Browser Extension 操作 Apify Actor 页面，先确认正确官网 domain，再收集公开网页信息、运行 Apify 背调 Actor，并生成可交付的多 Sheet .xlsx 背调报告。触发场景包括“帮我背调这家公司”“查一下某国家某公司”“国家+公司名做背调”“生成公司背调xlsx”“用Apify跑这个公司官网”等。
---

# 公司背调 XLSX

这个技能把“国家 + 公司名”变成一份可交付的公司背调 `.xlsx`。核心原则是：先确认公司官网，再用公开网页证据和 Apify Actor 结果交叉验证，最后只交付有来源、有空值标记、不编造的 Excel 报告。

## 输入

用户通常只提供两项：

```json
{
  "country": "国家或地区，例如 UAE / United Arab Emirates / 美国 / Germany",
  "company_name": "公司名，例如 Yellow Door Energy"
}
```

如果缺少国家或公司名，先用一句话补问。不要一开始问行业、联系人、邮箱、规模等额外条件。

## Tool Summary

| 步骤 | Use tool | 用途 |
| --- | --- | --- |
| 0 | local file read | 先读 `user.md` / `memory.md` 获取【我司信息】；找不到再用 `ask_user` 询问 |
| 1 | `web_search` | 搜索国家 + 公司名，围绕十章节报告维度找官网、公司、社媒、产品、实力、进口、风险、竞品等公开线索 |
| 2 | `ask_user` | 搜索结果有多个候选公司、多个官网、国家不匹配，或缺少【我司信息】时，让用户确认/补充 |
| 3 | `web_fetch` | 抓取官网、About、Contact、News、Team、LinkedIn/目录页、社媒、项目、进口/合规/行业来源等公开页面正文 |
| 4 | Browser Extension | 打开 Apify Actor 输入页并运行 Actor：`https://console.apify.com/actors/IoSHqwTR9YGhzccez/input` |
| 5 | `scripts/build_report_xlsx.py` | 把网页证据和 Apify 结果合并成 `.xlsx`；Apify 里重复的公司固定字段上提，联系人明细只保留 BD 有用字段，并执行 Excel 安全校验 |

Browser Extension 的精确工具名以 Accio 当前工具面板为准。运行时需要用到的能力只有：打开 URL、读取页面、点击、输入/粘贴文本、等待运行完成、读取或下载结果。不要索要或记录账号密码、敏感登录凭据或系统内部实现。

## 总流程

按顺序执行。前一步没有足够证据时，停下来确认，不要硬往后做。

### 第 0 步：读取我司信息

先尝试从当前 Accio / Agent 可访问的 `user.md`、`USER.md`、`memory.md`、`MEMORY.md` 中读取【我司信息】。

重点提取：

- 我司公司名
- 主营产品
- 目标市场
- 认证/资质
- 价格定位
- 样品/交期/MOQ
- 竞争优势
- 现有客户或案例
- 不适合开发的客户类型

如果找不到对应内容，不要编造。用 `ask_user` 补问：

```json
{
  "question": "我没有找到【我司信息】，请补充用于判断合作价值的核心资料。",
  "fields": [
    "我司主营产品",
    "主要优势",
    "目标市场/客户类型",
    "认证或资质",
    "常用报价/MOQ/样品策略"
  ]
}
```

如果用户暂时不补充，继续生成报告，但第八、九部分必须明确写“未找到我司信息，需补充后判断”，不能硬套产品匹配结论。

### 第 1 步：解析用户目标

提取：

- `country`
- `company_name`

生成搜索查询：

```text
"{company_name}" "{country}" official website
"{company_name}" "{country}" company
"{company_name}" "{country}" LinkedIn
"{company_name}" "{country}" contact
"{company_name}" products services pricing
"{company_name}" projects customers case study
"{company_name}" CEO founder management team
"{company_name}" import data supplier customs
"{company_name}" reviews Google Maps
"{country}" "{industry_or_product}" import trend China HS code
"{country}" "{industry_or_product}" certification tariff compliance
```

### 第 2 步：用 web_search 找官网候选

Use tool: `web_search`

优先用 Google 搜索。`web_search` 的 payload 里只需要变化 `query` 和 `api`，固定服务字段按工具 schema 默认填写即可。

示例入参形状：

```json
{
  "fieldName_3": {
    "payload": {
      "query": "\"Yellow Door Energy\" \"United Arab Emirates\" official website",
      "api": "google"
    }
  }
}
```

从搜索结果里提取候选：

| 字段 | 说明 |
| --- | --- |
| `候选名称` | 搜索结果标题里的公司名 |
| `候选官网` | 公司自己的主页 URL |
| `国家线索` | 页面摘要、地址、域名、结果标题中出现的国家/地区 |
| `来源类型` | 官网、LinkedIn、新闻、目录、工商、招聘、社媒、其他 |
| `置信度` | 高 / 中 / 低 |

官网判断规则：

- 优先公司自己的官网，不要把 LinkedIn、Crunchbase、目录站、招聘页、新闻页当官网。
- 优先 `https://` 的根域名，例如 `https://www.yellowdoorenergy.com/`。
- 删除 UTM、搜索参数、锚点和过深路径。
- 如果 `www` 是官方首页，就保留 `www`；如果跳转到裸域名，就用跳转后的域名。
- 最终 Apify input 必须是完整 domain URL，不是公司名、不是 LinkedIn、不是目录页。

### 第 3 步：必要时用 ask_user 确认

Use tool: `ask_user`

只在下面情况使用：

- 搜索结果出现多个同名公司。
- 国家与公司结果不一致，例如用户说 UAE，但结果主要指向 Saudi/UK/US 公司。
- 官网候选超过 1 个，且无法根据证据确定。
- 搜索结果只有目录页，没有明确官网。

问题要短，选项要带证据：

```json
{
  "question": "我找到多个可能的公司官网，请确认要背调哪一个？",
  "options": [
    {
      "id": "a",
      "label": "https://www.example.com/",
      "description": "搜索结果显示公司名一致，地址在 UAE。"
    },
    {
      "id": "b",
      "label": "https://www.example.co/",
      "description": "同名公司，但结果显示国家是 UK。"
    }
  ],
  "defaultOptionId": "a"
}
```

用户确认前不要运行 Apify Actor。

### 第 4 步：用 web_fetch 抓取公开网页证据

Use tool: `web_fetch`

至少抓取这些页面；没有就跳过并记录“未找到可靠公开信息”：

1. 官网首页
2. About / Company / Who we are
3. Contact / Offices / Locations
4. Products / Services / Solutions
5. News / Press / Blog
6. Team / Leadership / Management
7. Projects / Customers / Case studies
8. LinkedIn、Facebook、Instagram、YouTube、X/Twitter 等社媒主页
9. Google Maps / review / directory 页面
10. 进口数据、HS code、关税、认证、合规、行业进口趋势来源
11. 搜索结果里可靠的第三方页面，例如工商/目录、新闻报道、融资/股东信息、竞品列表

示例：

```json
{
  "urls": [
    "https://www.yellowdoorenergy.com/",
    "https://www.yellowdoorenergy.com/about/",
    "https://www.yellowdoorenergy.com/contact/"
  ],
  "timeout_seconds": 30
}
```

每个页面抽取这些信息：

| 字段 | 抽取要求 |
| --- | --- |
| 公司简介 | 原文要点，必要时翻译成中文摘要 |
| 主营业务 | 产品、服务、解决方案 |
| 国家/地区 | 总部、办公室、服务市场 |
| 联系方式 | 邮箱、电话、地址、Contact 页面 |
| 管理层/团队 | 只记录页面明确出现的人名和职位 |
| 客户/项目/案例 | 只记录页面明确出现的客户、项目名、行业或地区 |
| 规模线索 | 员工数、项目数、门店/渠道、营收、融资、市场覆盖 |
| 产品和价格 | 产品系列、材质/工艺/功能、公开价格、折算人民币价格 |
| 社媒数据 | 主页链接、粉丝数、帖子/视频数、活跃度 |
| 决策人员 | Founder/CEO/Owner/Managing Director/Purchasing/Product/Sales/Buyer/Import Manager |
| 进口和采购环境 | 公司层面进口记录优先；没有则国家/行业进口趋势、HS code、来源国、中国供应商地位、认证/关税/合规 |
| 风险/异常 | 负面新闻、官网无法访问、域名不匹配、信息过旧、来源冲突 |
| 来源 URL | 每条关键信息必须带 URL |

不要编造缺失信息。没有抓到就写 `未找到可靠公开信息`。

进口数据有硬边界：

- 必须明确说明“公司层面进口数据是否找到”。
- 优先查公司层面的进口记录、进口产品、HS Code、供应商国家、供应商公司、频率、规模。
- 如果公司层面找不到，只能改为国家/行业层面分析。
- 不得把国家/行业层面数据伪装成公司层面数据。

### 第 5 步：用 Browser Extension 运行 Apify Actor

Use tool: Browser Extension

打开这个页面：

```text
https://console.apify.com/actors/IoSHqwTR9YGhzccez/input
```

操作规则：

1. 如果页面要求登录，让用户先完成 Apify 登录；不要索要或记录账号密码。
2. 只输入已确认的完整官网 domain URL，例如：

```text
https://www.yellowdoorenergy.com/
```

3. 不要输入公司名、国家、LinkedIn、目录页、邮箱或其他筛选条件。
4. 读取页面当前显示的计费方式、套餐限制和预计运行规模；向用户展示 Actor、domain、可见价格/额度影响。只有用户明确确认本次可能计费的运行后，才点击运行 Actor。页面未显示可核实价格时要直说“费用未知”，不能替用户默认承担。
5. 等待运行完成。如果页面显示失败、额度不足、登录失效或 Actor 不可用，记录失败原因，不要伪造结果。
6. 读取或下载 Actor 输出。若页面只显示预览，优先进入 Dataset / Output 读取完整结果。

#### Apify domain 失败后的备用域名流程

一家公司可能同时使用多个域名，例如官网主域名、旧域名、地区站、品牌站、招聘/投资者站、API/CMS 域名或不带 `www` 的变体。Apify Actor 对某个 domain 返回 0 条、失败、无法识别公司，或返回明显不匹配公司时，不要立刻结束。

先用 `web_search` / `web_fetch` 重新找备用 domain：

```text
"{company_name}" official domain
"{company_name}" website
"{company_name}" contact domain
"{company_name}" old domain
"{company_name}" regional website {country}
"{company_name}" LinkedIn company website
site:{confirmed_root_domain_without_www} "{company_name}"
```

候选来源包括：

- 官网页面的 canonical URL、跳转后的 URL、footer 域名。
- LinkedIn 公司页的 Website 字段。
- 官方社媒 About / Profile 里的网址。
- 官网引用的 CMS/API/CDN 域名，但只有在明显属于该公司且能代表业务站点时才作为候选；不要把纯静态资源 CDN 当首选。
- 新闻稿、目录站、Google Maps、工商/注册页面里的公司网址。
- `www.example.com` / `example.com` / 国家地区子域名等变体。

处理规则：

1. 最多尝试 3 个高置信备用 domain。
2. 每次尝试都记录 `domain`、来源、为什么尝试、Apify 状态、返回数量。
3. 如果备用 domain 超过 1 个且无法判断优先级，用 `ask_user` 让用户选择。
4. 如果所有 domain 都失败，继续生成报告，但 `联系信息` 和 `背调报告` 的风险/待确认内容里写明已尝试的 domain 和失败原因。
5. 不要为了让 Apify 成功而输入 LinkedIn、目录页、新闻页或公司名。

如果 Browser Extension 能打开 Apify 页面，但无法稳定点击、输入、读取页面或接管标签页（例如页面加载很久、DOM 不可读、操作超时），不要反复等待或误点运行按钮。先记录：

```json
{
  "apify_status": "Browser Extension 已打开页面，但无法稳定操作，未启动运行",
  "apify_input_domain": "https://www.yellowdoorenergy.com/"
}
```

然后用 `ask_user` 询问用户是否要手动在 Apify 页面运行并把结果贴回，还是跳过 Apify 继续生成只有 web 证据的背调报告。用户没有明确确认前，不要点击会启动 Actor 的按钮。

保存状态：

```json
{
  "apify_actor_url": "https://console.apify.com/actors/IoSHqwTR9YGhzccez/input",
  "apify_input_domain": "https://www.yellowdoorenergy.com/",
  "apify_domain_attempts": [
    {
      "domain": "https://www.yellowdoorenergy.com/",
      "source": "官网 / LinkedIn / 社媒 / 目录",
      "reason": "为什么选择这个 domain",
      "status": "SUCCEEDED / FAILED / 0 rows",
      "returned_count": 84
    }
  ],
  "apify_status": "SUCCEEDED / FAILED / 未返回",
  "apify_failure_reason": "如果失败，写具体原因",
  "apify_raw_items": []
}
```

### 第 6 步：合成背调判断

根据 web 和 Apify 结果做交叉验证：

- 如果官网、国家、公司名三者一致，标记“官网确认：高”。
- 如果官网一致但国家线索较弱，标记“官网确认：中”，在待确认项说明。
- 如果 Apify 返回的公司名/domain 与 web 证据冲突，标记为风险，不要强行合并。
- 如果第三方来源和官网信息冲突，优先以官网为主，但把冲突写入“待确认/风险”。
- 结论要区分“已证实”“推测”“未返回”。

### 第 6.5 步：填写十章节背调报告

最终 XLSX 的第一张 Sheet 必须是 `背调报告`，按下面十个章节输出。每一行都要有：

| 列 | 说明 |
| --- | --- |
| 项目 | 章节内字段名 |
| 内容 | 结论或“未找到可靠公开信息” |
| 依据/来源 | 支撑该结论的 URL、来源名或“合理推测依据” |
| 信息属性 | 公开信息 / 合理推测 / 第三方数据 / 待确认 / 未找到可靠公开信息 |

固定章节：

1. `一、客户类型判断`
2. `二、公司介绍`
3. `三、公司实力分析`
4. `四、产品线与销售能力`
5. `五、关键决策人员与联络建议`
6. `六、近3年进口相关数据与采购环境`
7. `七、风险与注意事项`
8. `八、对【我司】的合作价值与切入建议`
9. `九、开发话术建议`
10. `十、主要来源`

第八、九部分必须结合【我司信息】。如果 `user.md` / `memory.md` 里没有、用户也没有补充，就只做条件判断，例如“若我司供应 X，则价值高；若不是该类产品，则价值低”，并标注为待确认。

### 第 7 步：整理联系人结果

Apify Actor 结果里通常会把公司字段重复到每一条联系人记录里。最终 XLSX 不要把这些字段在联系人表里反复展示，否则业务读者会很难扫描。

处理规则：

1. 把稳定重复的公司固定字段提取到 `联系信息` Sheet 顶部，放在 Actor 状态区下面。
2. 公司固定字段包括：公司名、官网、domain、行业、员工规模、公司 LinkedIn、成立年份、电话、地址、总部国家/城市、年收入、融资总额、关键词、公司描述、技术栈。
3. 联系人明细只展示业务开发有用字段：BD 优先级、评分、姓名、职位、工作邮箱、LinkedIn、建议原因、层级、职能、城市、州/省、联系人国家。
4. 不展示或默认移除这些重复/低价值字段：`first_name`、`last_name`、`mobile_number`、`personal_email`、`company_linkedin_uid`、`company_street_address`、`company_postal_code`、原始 revenue/funding 数字字段，以及所有已经上提的 `company_*` 固定字段。
5. 如果用户明确要求销售线索原始表，再单独保留全字段原始数据；否则最终背调 XLSX 以精简表为准。

#### B2B Business Development 联系建议

在 `联系信息` Sheet 顶部增加 `B2B Business Development 联系建议` 小表，并把建议优先联系的人在联系人明细中高亮。

推荐逻辑：

- 优先：CEO / Founder / Chief / President、C-suite、VP、Director、Head、Business Development、Commercial、Sales、Partnership、Procurement、Sourcing、Purchasing、Supply Chain、Project / Operations / Engineering 负责人。
- 加分：有公司域名工作邮箱、有 LinkedIn、职位与采购/合作/项目落地相关。
- 降权：HR、Recruiter、Talent、Intern、Assistant、缺少工作邮箱且职位影响力低。
- 输出要写清楚“为什么优先联系”，例如“有工作邮箱；邮箱域名匹配；决策层/创始人；公司决策职能”。
- 高优先级联系人必须在联系人明细表中用醒目底色高亮。
- `联系信息` Sheet 不要在联系人表头附近冻结窗格。深度冻结会让 Excel 滚轮像被锁住；保持普通可滚动视图即可。

### 第 7.5 步：生成开发行动计划

在 `开发行动计划` Sheet 把背调结论转成业务员下一步能执行的动作。这个 Sheet 默认展示给用户，不要隐藏。

固定列：

| 列 | 说明 |
| --- | --- |
| 阶段 | 线索确认、首轮触达、产品切入、报价与样品、跟进节奏、待问问题、风险控制、邮件草稿 |
| 行动项 | 需要执行的具体动作 |
| 建议内容 | 具体怎么做；可包含首要联系人、备用联系路径、推荐产品、卖点、报价/样品策略、英文开发信 |
| 对象/负责人 | 业务员、客户、产品、或需要联系的具体人 |
| 优先级 | 高 / 中 / 低 / 待确认 |
| 依据/备注 | 来自哪一部分报告、联系人评分或公开证据 |

行动计划至少要包含：

1. 确认主体和官网。
2. 优先联系人和备用联系路径。
3. 推荐切入产品与首封卖点。
4. 报价策略、样品策略、认证或资料准备。
5. 后续跟进节奏。
6. 最应该问客户的 3 到 5 个问题。
7. 优先核验风险。
8. 可直接复制修改的英文开发信。

## XLSX 交付结构

最终只交付 `.xlsx`。默认文件名：

```text
公司背调_{country}_{company_name}_{YYYY-MM-DD}.xlsx
```

固定 Sheet 只有 3 个，全部可见：

| Sheet | 内容 |
| --- | --- |
| `背调报告` | 按十章节输出客户类型、公司介绍、实力、产品线、决策人、进口环境、风险、合作价值、开发话术、主要来源 |
| `联系信息` | Actor 输入、运行状态、去重后的公司固定字段、B2B 联系建议、精简联系人明细和高亮优先联系人 |
| `开发行动计划` | 把背调结论转成业务开发动作：优先联系人、备用路径、产品切入、报价/样品、跟进节奏、待问问题、风险核验和英文开发信 |

不要创建 `背调摘要`、`公司画像`、`网页证据`、`风险待确认` 等辅助底表，也不要创建隐藏 sheet。网页证据、风险和来源都整理进 `背调报告`，联系人和 Actor 运行信息整理进 `联系信息`。

生成 XLSX 前先整理一个 JSON：

```json
{
  "input": {
    "country": "United Arab Emirates",
    "company_name": "Yellow Door Energy"
  },
  "confirmed_company": {
    "official_name": "Yellow Door Energy",
    "official_domain": "https://www.yellowdoorenergy.com/",
    "country_match": "高",
    "confidence": "高"
  },
  "summary": {
    "risk_level": "低 / 中 / 高 / 待判断",
    "conclusion": "一句话结论",
    "key_findings": ["要点1", "要点2"]
  },
  "structured_report": {
    "一、客户类型判断": {
      "客户类型": {
        "answer": "结论",
        "basis": "来源 URL 或推测依据",
        "info_type": "公开信息 / 合理推测 / 待确认"
      }
    }
  },
  "company_profile": {
    "business": "主营业务",
    "locations": "国家/地区",
    "contacts": "联系方式",
    "management": "管理层",
    "projects_or_clients": "客户/项目"
  },
  "web_evidence": [
    {
      "source_type": "官网/About/新闻/目录/LinkedIn",
      "title": "来源标题",
      "url": "https://example.com",
      "fact": "抽取到的事实",
      "confidence": "高 / 中 / 低"
    }
  ],
  "apify": {
    "actor_url": "https://console.apify.com/actors/IoSHqwTR9YGhzccez/input",
    "input_domain": "https://www.yellowdoorenergy.com/",
    "status": "SUCCEEDED",
    "raw_items": []
  },
  "risks": [
    {
      "risk": "风险或待确认项",
      "reason": "为什么需要确认",
      "source_url": "https://example.com"
    }
  ]
}
```

调用脚本：

```bash
python3 "$SKILL_ROOT/scripts/build_report_xlsx.py" \
  --input ./company_background_report.json \
  --output "./公司背调_United-Arab-Emirates_Yellow-Door-Energy_2026-05-25.xlsx"
```

交付前必须让脚本完成：

- LibreOffice headless 重存。
- 清理 `xl/tables/`、空 `xl/drawings/`、`tableParts` 和 drawing/table relationships。
- 通过 `unzip -t`。
- 通过 `openpyxl.load_workbook()`。
- 扫描包内 table/drawing 残留。

任一步失败，禁止把 `.xlsx` 当最终结果交付；先修复或告诉用户当前只能交付中间 JSON。

## 最终回复模板

```markdown
已完成公司背调，并生成 XLSX：

- 公司：{official_name}
- 国家/地区：{country}
- 已确认官网：{official_domain}
- Apify 状态：{apify_status}
- 风险等级：{risk_level}
- 文件：{xlsx_path}

备注：未返回的信息已在表格里标为“未返回”，没有编造邮箱、电话、管理层或项目。
```

## 禁止事项

- 不要把 LinkedIn、目录站、新闻页当作 Apify input。
- 不要用公司名替代 domain 跑 Actor。
- 不要编造邮箱、电话、地址、管理层、融资、客户、项目或负面新闻。
- 不要在最终用户报告里暴露登录凭据、认证信息或系统内部实现。
- 不要只给聊天总结；最终必须有 `.xlsx`，除非工具/账号/环境失败并已明确告知。
