# 新品审批门禁

## 触发词

新品上架前检查、发品门禁、新品审批。

## 先读哪些证据

- `query_user_category`：确认用户可经营/发布类目。
- `data_advisor_category_prediction / data_advisor_category_infer`：预测候选类目。
- `query_attribute_info` + `query_attribute_options_info`：按属性类型获取定义，再按属性 ID 获取系统选项。
- `material_analysis / query_material_analysis_result`：解析用户素材。
- 外部 URL 发品时才使用 `precheck_url_product_generate` 检查数量、额度和图片空间；已有草稿复盘不把 URL 预检当通用门禁。

## 判断方式

资料缺失时不得放行；发品动作交给 auto-product-publisher。

校准规则：没有可迁移数字阈值时，只做定性分级，并写明需按行业、店铺历史或用户确认口径校准。

## 执行步骤

1. 先确认目标是方案、草稿、提交还是正式发布；默认只做方案/草稿。
2. 用类目和属性工具建立必填字段清单。
3. 解析素材后标已满足、待确认和缺失字段。
4. 输出新品门禁结论、缺口和可进入草稿的条件。
5. 创建草稿、提交或正式发布必须逐步确认。

## 输出重点

放行/待补/阻断清单。

## 常见误判

- 证据不足时给确定结论。
- 把建议动作写成已执行动作。
- 没有区分用户确认前后的边界。
- 把本子场景扩展成完整店铺报告或其他专门流程的交付物。
