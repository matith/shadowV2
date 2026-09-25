# Future Capability Reservation

以下能力 **只预留边界，不在 P0/P1 提前施工**。新增时走 Capability Registry，不得推翻 Ledger Core。

| 能力 | 预留落点 | 备注 |
| --- | --- | --- |
| 图片 / OCR | Capability → File/Source | 原文仍进 Source |
| 语音 | Interaction Channel + Capability | 转写后仍是 Event/Source |
| PDF / Word / PPT / Excel | Capability + File Source | 解释进 Knowledge/Product |
| 邮件 / 日历 | Interaction / Durable / Capability | 不绑死业务状态 |
| 浏览器 / 网盘 / 文件夹 / PC 上下文 | Capability + Source | 自动归档需 Directive 约束 |
| 企业微信 / 分享 / App / 扩展 | Interaction Layer | Channel 可替换 |
| 产品知识库 / 人际关系 / 长期项目 | 已在 Ledger taxonomy | 不另立真源 |
| 工作流 | Capability + Durable | 避免固定决策树绑架模型 |
| Background Agent | Memory Fabric / Operations | 不得改 Source |
| 多模型 / 本地模型 | Model Adapter / Ops Config | 可替换 |
| MCP / 第三方插件 | Capability Registry | Tool Contract + Permission |
| WPS / 多维表 | Projection Adapter | 非真源 |

## 新增能力检查单

1. 是否污染 Canonical？
2. 是否破坏 C1–C12？
3. 是否可替换/可重建？
4. 是否只影响一个黑盒内实现？
5. P 阶段是否真需要现在做？
