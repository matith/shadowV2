# Acceptance Scenarios

每个场景都是 **长期产品能力验收**，不是单测示例。P0 至少打通 A/C/E 的最小闭环；其余可分期，但架构必须能自然支持。

---

## Scenario A — 日常承诺

**用户：** “明天下午提醒我联系李经理，合同还没盖章。”

**期望：**

1. 生成 Event（用户要求提醒 + 合同未盖章）
2. 打开/更新 Matter「合同盖章」
3. 记录 People「李经理」
4. 创建 Reminder（明天下午）
5. 维护 Context Capsule
6. 次日提醒送达
7. 用户说“联系了，他说周一盖” → 同一 Matter 更新，不新建重复事项
8. 之后询问能恢复当前状态

**通过标准：** Matter/People/Reminder/Event/Capsule 齐备且可追溯；多轮收敛到同一 Matter。

---

## Scenario B — 长期资料

**用户：** 上传重要产品资料（如云电脑政策 PDF）。

**期望：**

1. 进入 File/Source Ledger（保留原文）
2. 进入 Product / Business Ledger，必要时关联 Knowledge
3. **不**被当成临时聊天 Matter 烧掉
4. 过很久仍可检索：“上次那份云电脑政策说了什么？”
5. 回答可追溯到 Source/File

**通过标准：** 资料生命周期是长期的；检索走 Knowledge/Product/File，而不是只靠聊天回忆。

---

## Scenario C — 多轮事项

**用户：** 数天内连续更新同一事项（春促启动会）。

**期望：**

1. 始终维护同一 Matter
2. 新 Event 追加历史
3. Matter 当前状态/Capsule 增量更新
4. 不生成重复事项
5. 下一步/开放项保持准确

**通过标准：** 同一事项多日演进仍收敛单一 Matter 主体（子事项除外）。

---

## Scenario D — 子事项

**结构：** 春促启动会 → PPT → 领导页/颁奖页；以及主持稿。

**期望：**

1. 树状 Matter 可表达
2. 子事项变化只增量影响祖先 Capsule
3. 不重扫整树
4. 父级能看见子级摘要与 dirty 结果

**通过标准：** 局部变更、局部传播；无变化即停。

---

## Scenario E — 纠正

**用户：** “不是王经理，是李经理。” / “不是周一，是周三。”

**期望：**

1. Source 不改
2. 旧 Interpretation 失效
3. Correction 记录
4. Current State 用新值
5. 后续 Context 不再用错误值

**通过标准：** 纠正后状态一致；审计可查；无“改原文”捷径。

---

## Scenario F — 归档召回

**用户：** 数月后问“当年那个春促……”

**期望：**

1. Archive 极小摘要命中“有这回事”
2. 可按需展开完整 Matter/Event/File
3. 不必预先把全历史放进日常上下文

**通过标准：** 归档可召回、可下钻、成本可控。

---

## Scenario G — 多 Ledger

**用户：** “李经理发来新的云电脑产品政策 PDF，下月生效，和我们在谈的项目有关。”

**期望：** 同一次处理可建立：

- People: 李经理
- Product: 云电脑
- Knowledge/File: 新政策
- File/Source: 原 PDF
- Event: 收到资料
- Matter: 关联到进行中项目（若相关）

**通过标准：** 多账本引用连接，无强制单分类；原文只存一份。

---

# 额外工程验收（横切）

| ID | 项 | 通过标准 |
| --- | --- | --- |
| X1 | 幂等 | 重复提交操作不双写 Matter/Reminder |
| X2 | 可追溯 | Capsule → Evidence → Source |
| X3 | 可替换 | 换模型/Provider 后 Core 语义不变 |
| X4 | 可恢复 | Derived 全丢可从 Canonical 重建 |
| X5 | 预算 | 长期数据增长后单次 Working Context 仍受控 |
| X6 | 高风险确认 | 对外发送/删除/金额类有确认；日常整理不刷屏 |
