# 阿里官方五条 Sell Point 默认参考格式

用户没有指定维度时，默认按本文件的五维顺序生成。模板只规定内容结构，不提供产品事实；缺失内容必须先询问，或用已确认的商家优势替换并说明原因。

## 1. 产品核心亮点

突出产品最主要的卖点或创新点，说明最具吸引力、最有差异的特性，明确传递核心价值。

```text
<Core Highlight>: <most important confirmed feature or innovation> helps <target buyer> achieve <clear buyer value>.
```

结构示例：`Active Noise Cancellation: ANC technology helps reduce ambient sound so users can focus on music and calls.`

## 2. 重要功能或特性说明

呈现关键功能和用途，介绍产品的实用性以及该功能能给顾客带来的利益。

```text
<Key Function>: <confirmed function and how it works> provides <practical benefit> for <relevant use>.
```

结构示例：`Touch Control and Transparency Mode: Tap controls simplify playback and calls while transparency mode helps users hear their surroundings.`

## 3. 材质、规格、尺寸等主要属性

自然描述产品的主要材料、规格、容量、尺寸、重量、版本或兼容性，让顾客判断是否匹配采购需求。不得补造数字或型号。

```text
<Material or Specification>: <confirmed material, size, capacity, weight, version, or compatibility> supports <matching or performance benefit>.
```

结构示例：`Bluetooth 5.0 Connection: Confirmed Bluetooth 5.0 compatibility supports stable pairing with the stated devices.`

## 4. 场景适用与用户体验

说明适用人群或场合，以及产品使用的便捷性、舒适性或体验优势。

```text
<Application or Experience>: Designed for <confirmed audience or scenario>, offering <confirmed convenience or experience benefit>.
```

结构示例：`Lightweight In Ear Fit: Multiple confirmed ear tip sizes improve fit and comfort for commuting and longer listening sessions.`

## 5. 配件、使用与服务支持

说明产品是否附带操作说明、配件或支持渠道，突出简单易用。不得承诺用户没有确认的售后、保修、退换或长期服务。

```text
<Accessories or Support>: Includes <confirmed accessory, guide, setup, or support channel> to help buyers or users <practical benefit>.
```

结构示例：`Charging Case and Easy Setup: The confirmed package includes a charging case, cable, ear tips and user guide for convenient setup and daily use.`

## 替换规则

默认先尝试补齐上述五维。出现以下情况时允许替换：

- 产品没有配件或支持信息：用已确认的定制、质量、包装或交付优势替换第 5 条。
- 第 1、2 条容易重复：第 1 条聚焦核心差异，第 2 条聚焦另一个具体功能及其用途。
- 材质规格信息不足：使用 `ask_user` 补问；不得用行业常见参数填充。
- 用户明确要求突出定制、工厂或质量：替换最不相关的默认维度，并在输出前说明采用的五个维度。

## 输出格式

每条均使用：

```text
Short Heading: Natural English explanation of the confirmed feature and buyer value.
```

示例只展示结构，不得把耳机示例中的 ANC、Bluetooth 5.0、配件或功能套用到其他产品。
