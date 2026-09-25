# -*- coding: utf-8 -*-
"""UX / practical-delivery pass over 拾光 module specs (from the user's seat)."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:4319"
PID = "11dd729c-beaa-42cf-bad1-a06ab4f89e1b"
ACTOR = {"actor_id": "mimo-sol-shiguang-v2", "actor_role": "AI"}


def status_gen():
    req = urllib.request.Request(BASE + "/api/repo-status")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["repository_generation"]


def call(method, path, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json", "X-BBM-Expected-Project-Id": PID},
        method=method,
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def write(method, path, make_body, attempts=8):
    last = None
    for _ in range(attempts):
        gen = status_gen()
        s, b = call(method, path, make_body(gen))
        if s < 300:
            return s, b
        code = (b or {}).get("error", {}).get("code") if isinstance(b, dict) else None
        last = (s, b)
        if code == "GENERATION_CONFLICT":
            time.sleep(0.12)
            continue
        return s, b
    return last


def spec(purpose, kind, narrative, outcomes, failures, constraints, custom):
    return {
        "purpose": purpose,
        "acceptance_experience": {
            "kind": kind,
            "narrative": narrative,
            "expected_outcomes": outcomes,
            "failure_signals": failures,
        },
        "constraints": constraints,
        "custom": custom,
    }


# 全部从「用户坐在屏幕前会不会觉得好用」重写
MODULES = {
    "interaction-layer": {
        "name": "交互层",
        "summary": "用户无论从企微、App 还是 Web 说话，都像在跟同一个「拾光」说话；消息、附件、提醒送达可靠，不在渠道间丢失或串号。",
        "spec": spec(
            purpose=(
                "交互层要消除「换个入口就失忆/丢件」的体验断裂。用户不该理解 Channel、Webhook、会话 ID；"
                "他只需要：说一句话、传一个文件、收到回复和提醒。因此交互层必须把多渠道输入收成统一信封，"
                "把回复送回用户真正会看的那个入口，并在渠道抖动时给用户可感知但不过度的反馈（正在重试/已记下/稍后补送）。"
            ),
            kind="user_journey",
            narrative=(
                "【好用的样子】早上 9:02 企微说「下午三点提醒我给李经理回电话」；9:10 在 Web 补「合同还没盖章」；"
                "12:30 在 App 甩一张报价单截图。下午 3:00 提醒出现在他最常用的企微（或手机通知），点开能直接看到"
                "「联系李经理｜合同盖章」卡片，而不是一串查不到前文的系统文本。"
                "【难用的样子】同一件事在三个渠道变成三套「草稿」；提醒发到昨天那个会话；截图传了但事后「没有这个文件」。"
            ),
            outcomes=[
                "用户用口语说事项/补充/传文件，不要求他先选「写入哪个账本」",
                "同一用户跨渠道 3 次输入，在体验上是「同一个拾光记了三笔相关补充」，不是三段无关聊天",
                "提醒/回复送达用户当前会用的入口；失败可见（「未送达，已重试」）且可补送",
                "附件在聊天里可点开，且在账本证据链里仍能找到原件",
                "网络抖动/渠道限流时，用户仍感到「已经记下」，不会静默丢单",
            ],
            failures=[
                "用户必须自己记住「这事我是在企微说的」才能找回上下文",
                "提醒发到错误会话或错误设备，错过关键节点",
                "图片/PDF 显示已发送，账本里却只有「有一条附件」没有文件",
                "渠道失败后彻底无反馈，用户以为已保存",
                "为适配某渠道排版/长度，悄悄截断用户原话",
            ],
            constraints=[
                "用户可见文案禁止暴露 Channel 内部 ID/错误码，可保留可复制的追踪号",
                "跨渠道身份合并必须可解释；合并错误必须能一键「拆开/改绑」",
                "提醒送达目标优先「用户最近活跃且开启通知的入口」，可被用户指定覆盖",
                "附件必须可下载/预览；保存失败要立刻可感知，禁止假装成功",
                "任何渠道重试不得让用户感到重复提醒轰炸（合并去重）",
            ],
            custom={
                "responsibilities": ["跨渠道一致会话感", "可靠送达", "附件不丢", "失败可感知"],
                "actions": [
                    "normalize_inbound_message",
                    "deliver_reply",
                    "deliver_notification",
                    "store_attachment_preview",
                    "merge_user_identity_across_channels",
                    "resend_failed_delivery",
                ],
                "user_moments": [
                    "通勤路上用手机补一句，到工位 Web 里能接着聊",
                    "到了提醒时间，手机响了，点开就是事项卡",
                    "传完 PDF 后，「以后查」不用再找原聊天",
                ],
                "ux_scorecard": [
                    "找到一条历史消息 ≤ 2 步",
                    "提醒错过时有补送入口",
                    "跨渠道补话无需用户声明「这是同一事」",
                ],
                "in_scope": ["Channel Gateway", "Message Normalizer", "Delivery", "Notification targeting"],
                "out_of_scope": ["事项状态字段权威", "摘要生成", "是否记账的最终裁决"],
                "real_scenarios": [
                    "企微记事项 → Web 补充 → App 传图，提醒落在手机",
                    "渠道限流：用户看到「已记下，通知稍后补送」",
                ],
            },
        ),
    },
    "agent-runtime": {
        "name": "智能体运行时",
        "summary": "像一个懂你工作节奏的助理：一次把事说清、改完并确认；不反复问、不瞎写、不让你等五轮才把状态改对。",
        "spec": spec(
            purpose=(
                "用户不关心 harness 是谁。他关心：我说人话，拾光听得懂、改得对、回得快。"
                "运行时的好用标准是「单轮闭环」——理解、执行账本操作、用人话回复，尽量在一次交互里完成；"
                "只在真正高风险或信息缺口时才追问。模型/harness 可换，不能换掉这种体感。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】用户：「主持人改成王雨和胥晴，亮总放代理商后面。」拾光：「已更新春促启动会：主持人=王雨、胥晴；"
                "亮总措施在代理商分享后。要不要顺手改主持稿开场时间？」——一次说清、一次改完、顺带给下一步。"
                "【难用】先回「好的」，再问三个字段怎么填，最后状态还是旧的；或把「亮总」写成一个新事项。"
                "【纠正】「不是王雨，是王雨晴。」必须立刻改当前状态，并说清改了哪里，而不是解释半天规则。"
            ),
            outcomes=[
                "普通记账/改状态：用户平均 1 轮得到「已改好 + 改了什么」",
                "只在缺关键信息或高风险时追问，且一次问全（不要挤牙膏）",
                "纠正类输入有明确「已改正」反馈，并指出旧值 → 新值",
                "证据不足时明说「我没把握，依据是/想核实 X」，不编造",
                "慢操作（读长 PDF）给出进行感，避免假死",
            ],
            failures=[
                "万事皆确认：改个摘要也要用户点同意",
                "只确认不做：回复很像做了，账本没变",
                "纠正后还按旧理解回复",
                "把一次简单修改拆成多轮「请补充模板字段」",
                "深度长文思考导致简单改字段也卡很久",
            ],
            constraints=[
                "简单内部状态变更默认免确认；仅删除/对外发送/金钱/不可逆外发需确认",
                "Turn 产出必须可核对：Reply 文案与 Ledger Ops 列表一致（说了改就必须改）",
                "禁止用「作为 AI 我无法…」回避可做的账本操作",
                "模型失败/超时要有降级回复，不得无声结束",
                "追问模板默认一次最多 3 个问题，且可「先按最合理假设记上，之后改」",
            ],
            custom={
                "responsibilities": ["单轮闭环", "克制追问", "纠正体感", "假死防护"],
                "actions": [
                    "run_turn",
                    "emit_ledger_ops",
                    "confirm_high_risk_only",
                    "apply_correction_from_speech",
                    "show_change_digest",
                ],
                "user_moments": [
                    "一句话改主持信息，马上看懂改了什么",
                    "说错了名字，一句纠正就对齐",
                    "传长文件时知道「在读」而不是无响应",
                ],
                "ux_scorecard": [
                    "简单修改 1 轮完成率",
                    "追问轮数 ≤ 1（信息齐时）",
                    "回复中包含变更摘要（旧→新）",
                ],
                "in_scope": ["Model Adapter", "Tool Calling", "Turn Orchestration"],
                "out_of_scope": ["表格渲染", "提醒触发时机", "长期索引构建"],
                "real_scenarios": [
                    "单轮更新主持流程并给出下一步建议",
                    "口误纠正：王雨→王雨晴",
                    "长 PDF 合同：先给进度，再给要点+证据",
                ],
            },
        ),
    },
    "context-engine": {
        "name": "上下文引擎",
        "summary": "让你少重复自己：相关的人和事自己浮上来，无关旧事不刷屏；隐私和「别乱记」指令被真正执行。",
        "spec": spec(
            purpose=(
                "用户对「记忆」的体感是：拾光该知道的知道，不该缠的不缠。上下文引擎要让相关人物/事项/政策"
                "自动出现在该出现的时刻，同时遵守「闲聊别长期记」「晚上别推工作」等指令。"
                "预算与热度对用户应不可见，但结果要稳：重要长期事项永远捞得回来。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】提到「李经理的合同」，回复里自然带上：李经理是谁、合同卡在哪、上次谁说周几盖章。"
                "不需要用户再讲一遍背景。"
                "【隐私】用户说过「除非我明确说保存，否则闲聊不要长期记录」。打完游戏闲聊三天后，不应在工作上下文里"
                "冒出「你上周说想买显卡」。"
                "【长期】半年前的两年框架合同，问「联通那单怎么样了」仍能 3 秒内带出当前状态，而不是「我找不到」。"
            ),
            outcomes=[
                "提及相关人物/项目时，免重复介绍背景（背景可一点即查）",
                "用户明说「别记」的内容，后续工作对话不泄漏",
                "一次只带「用得上」的上下文，回复不被无关旧事淹没",
                "归档/冷记忆在用户提起时能捞回，而不是永远沉默",
                "被裁剪时，若关键上下文不足，运行时会标注「我不确定历史细节」",
            ],
            failures=[
                "每次都要用户重新介绍李经理是谁",
                "闲聊被当工作事实长期跟进",
                "重要合同只因「最近没聊」就再也召不回",
                "塞入大量无关历史，回复跑题",
                "用户说「别记了」，系统还在摘要里留着",
            ],
            constraints=[
                "Directive（不记/不提醒/优先归档规则）优先级高于召回相关性",
                "热度必须多因子，禁止「N 天外=冷」一刀切",
                "Working Context 对用户可解释：支持「你刚才用了哪些记忆」轻量回看",
                "涉及「别记/删除」的指令必须能作用于 Derived 与后续 Context，而非只回一句好的",
                "召回宁缺毋滥：低质量线索降权，而不是凑满上下文",
            ],
            custom={
                "responsibilities": ["该想起就想起来", "不该记就不记", "不刷屏", "长期事项可召"],
                "actions": [
                    "compile_working_context",
                    "route_to_ledgers",
                    "apply_directives",
                    "recall_relevant",
                    "explain_memory_sources_light",
                ],
                "user_moments": [
                    "开口谈合同，对方背景已就位",
                    "闲聊不进工作大脑",
                    "半年后再问老合同，还在",
                ],
                "ux_scorecard": [
                    "相关人物/事项自动带出率",
                    "工作对话中无关私人闲聊泄漏 = 0",
                    "用户重复介绍背景次数",
                ],
                "in_scope": ["Context Compiler", "Ledger Router", "Memory Retrieval", "Context Budget"],
                "out_of_scope": ["最终写入裁决", "渠道通知"],
                "real_scenarios": [
                    "「李经理合同」一开口就带背景卡",
                    "Directive：闲聊不长期保存被执行",
                    "归档合同被重新捞起",
                ],
            },
        ),
    },
    "personal-ledger-core": {
        "name": "个人账本核心",
        "summary": "像一张你敢信的「我的事」总表：状态永远是最新、同一件事不重复、能展开子项和证据；不用翻聊天考古。",
        "spec": spec(
            purpose=(
                "账本核心的好用，不是表多，而是「一眼知道我有多少事、每件事卡在哪、下一步是什么」。"
                "用户要的是可信的当前真相：同一事项多轮更新不劈叉，父子项目能收放，归档后还能想起。"
                "AI 只是帮填表的人，表本身永远站得住。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】打开表格/「我的事」：春促启动会（进行中｜下一步：核对获奖名单）、合同盖章（等待｜周一确认）…"
                "点进启动会能看到 PPT/主持稿子项、李经理、最近 3 条事件、附件。"
                "周四说「合同他说周一盖」→ 同一行状态更新，不出现「合同盖章 2」。"
                "两年后问「当年春促」→ 先给一行归档摘要，需要再展开。"
            ),
            outcomes=[
                "用户能在一处看到：进行中/等待/完成的事 + 下一步",
                "同名事项系统倾向合并/关联，而不是默默新建第二条",
                "子事项变更后，父事项摘要与开放项仍然正确",
                "任何结论可点开证据，表格与 AI 说法一致",
                "没有 Web 表格时，用对话问「我最近有什么事」也能得到同一真相",
            ],
            failures=[
                "列表里三条几乎一样的合同事项，不知道哪条是准的",
                "表格写着「进行中」，问 AI 却说「已完成」",
                "子项都做完了，父项还一直提示待办",
                "归档后用户再也调不出来",
                "只有聊天流，没有可浏览的当前状态",
            ],
            constraints=[
                "Matter 当前字段是单一事实来源；Event 只追加",
                "新建 Matter 必须做相似合并检查（标题/人物/时间），建议合并而非静默分裂",
                "表字段与 AI 读字段同源，禁止两套状态",
                "归档保留 title/state/capsule/指针，入口可发现",
                "用户可直接改状态字段，改动即时被 AI 看见",
            ],
            custom={
                "responsibilities": ["当前真相可读", "多轮收敛", "父子可展开", "证据可点"],
                "actions": [
                    "create_or_update_matter",
                    "suggest_merge_duplicate_matter",
                    "list_my_open_matters",
                    "expand_matter_tree",
                    "archive_with_mini_capsule",
                ],
                "user_moments": [
                    "早上扫一眼就知今天卡在哪几件事",
                    "接着昨天说，事项还是那一条",
                    "两年后还能找回「那个春促」",
                ],
                "ux_scorecard": [
                    "找到「我该做什么」≤ 10 秒",
                    "重复事项率低",
                    "人看表格 vs 问 AI 答案一致",
                ],
                "in_scope": ["Matter/Event/People/Knowledge/Product/File/Directive/Archive"],
                "out_of_scope": ["向量实现", "渠道排版", "模型风格"],
                "real_scenarios": [
                    "「我的事」总览与下一步",
                    "合同盖章 4 天更新收敛为一行",
                    "归档春促可召回",
                ],
            },
        ),
    },
    "source-evidence": {
        "name": "来源与证据",
        "summary": "AI 说的每句要紧话，你都能点回原文；改错不销毁原件，而是「新理解 + 旧理解作废」。",
        "spec": spec(
            purpose=(
                "用户要的是信任：要么有依据，要么承认没依据。来源与证据让「依据」可点、可下载、可核对，"
                "并保证纠正不会把原始记录改得面目全非。没有这一层，账本只是更整齐的传言。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】问「资费到底是多少？」答「29 元/月，依据：云电脑政策 V3.pdf 第 4 页」，点击直接打开定位。"
                "【纠正】你指出「是 39」→ 系统：「已按你更正为 39；原 PDF 仍保留；旧摘要已作废。」"
                "【没依据】问冷门细节时，答「我没在你的材料里找到，不想猜」，并给「上传/粘贴原文」入口。"
            ),
            outcomes=[
                "重要结论 100% 可跳转到原文/原话/原文件",
                "纠正后原件仍在，且能看到「曾经错在哪里」",
                "缺证据时明说，不硬答",
                "附件版本可分（V2/V3），不会被覆盖到「只剩最新」",
                "对话里引用的句子可一键复制出处",
            ],
            failures=[
                "答得很自信但点进去是空的/不对的文件",
                "「更正」变成直接改历史消息",
                "只有摘要文件，找不到政策原件",
                "缺证据时编造页码",
                "同名文件覆盖，旧版本丢失",
            ],
            constraints=[
                "Raw Source 只读；纠正只作用于解释与账本字段",
                "对外回答若带事实主张，必须带 evidence_refs 或明确「无依据」",
                "页码/段落定位优先；至少落到文件+章节",
                "删除用户数据走用户指令，不因「纠正」而删 Source",
                "存储缺失要报「证据损坏」，禁止静默用旧摘要顶替",
            ],
            custom={
                "responsibilities": ["可点回原文", "纠正不毁原件", "无依据就认", "版本不覆盖"],
                "actions": [
                    "store_raw_source",
                    "answer_with_evidence_refs",
                    "open_source_at_location",
                    "mark_interpretation_invalid",
                    "detect_missing_evidence",
                ],
                "user_moments": [
                    "汇报前点开依据页码",
                    "纠完费率，原件还在",
                    "AI 说「我没找到」而不是瞎编",
                ],
                "ux_scorecard": [
                    "结论→原文点击可达",
                    "无依据硬答率 = 0",
                    "纠正后原件保留率 = 100%",
                ],
                "in_scope": ["Raw Source", "Attachment", "Provenance", "Version"],
                "out_of_scope": ["美观摘要文案", "记忆检索排序"],
                "real_scenarios": [
                    "资费问答带 PDF 页码",
                    "更正 29→39 且保留原 PDF",
                    "材料没有时承认无依据",
                ],
            },
        ),
    },
    "state-commit-engine": {
        "name": "状态提交引擎",
        "summary": "你说的事被可靠记下：不重复、不丢、可改错；烦人的确认弹窗只留给真正危险的操作。",
        "spec": spec(
            purpose=(
                "用户体感中的「靠谱」几乎全在这里：说一次就只记一次，改一次就立刻准，"
                "系统说成功就是成功。提交引擎把体验承诺变成原子、幂等、可审计的变更，"
                "并用确认策略保护用户不被自己或 AI 的高风险动作误伤。"
            ),
            kind="user_journey",
            narrative=(
                "【连发】用户三条语音：「明天提醒我…还有合同…李经理。」应合并成 1 个提醒 + 1 个相关事项，而不是 3 条轰炸。"
                "【改错】「不是周一，是周三。」表里日期变周三，AI 之后都按周三说。"
                "【危险】AI 想给客户发邮件 → 先预览再发送；而「把状态改成等待」不应打断。"
                "【失败】保存失败必须说「没存上」，不能点头像成功。"
            ),
            outcomes=[
                "重复说/重试/弱网不双写",
                "用户一句话多意图（提醒+事项+人）一次落库",
                "纠正立即生效且有「变更回执」",
                "高风险才确认，日常修改零打扰",
                "失败可重试，且不会半套数据",
            ],
            failures=[
                "双提醒、双事项，用户不敢再说第二遍",
                "说「改周三」后系统还按周一提醒",
                "每个操作都「请确认」导致想关掉助手",
                "界面写成功，刷新后又变了",
                "高风险删除无确认",
            ],
            constraints=[
                "op_id 幂等；渠道/模型重放安全",
                "「成功」文案仅在 commit 落盘后出现",
                "确认策略白名单：默认免确认写摘要/关联/内部整理",
                "Correction 必须出现在变更回执（旧值→新值）",
                "半失败自动回滚或可续传，用户无感修复",
            ],
            custom={
                "responsibilities": ["不双写", "改了就准", "危险才拦", "失败说清楚"],
                "actions": [
                    "commit_ledger_ops",
                    "merge_conversation_burst",
                    "apply_correction",
                    "require_confirmation_for_high_risk",
                    "emit_change_receipt",
                ],
                "user_moments": [
                    "语音三连只出一条提醒",
                    "改日期后不再听错日子",
                    "误操作前被拦住",
                ],
                "ux_scorecard": [
                    "重复事项/提醒 = 0",
                    "确认弹窗频次低",
                    "成功回执与真实状态一致",
                ],
                "in_scope": ["Proposal", "Patch", "Correction", "Conflict", "Commit"],
                "out_of_scope": ["自然语言文风", "提醒 UI 长相"],
                "real_scenarios": [
                    "语音三连合并",
                    "周一→周三纠正",
                    "发信预览确认",
                ],
            },
        ),
    },
    "summary-system": {
        "name": "摘要系统",
        "summary": "给你的是「能干活的短状态」而不是作文：差什么、到哪了、谁负责，一眼能点开细节。",
        "spec": spec(
            purpose=(
                "摘要不是文学创作，是驾驶舱仪表。Context Capsule 要让用户和 AI 共享同一套"
                "「当前/变化/开放项/证据」。增量维护保证大项目越滚越长时，打开仍然快、改一处不折腾全家。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】问「启动会还差什么？」答：①获奖名单未定 ②抽奖规则待确认 ③PPT 与主持稿台词不一致；"
                "并注明「依据 event_38 / file_09」。不需要读完全部历史。"
                "【增量】只改了领导页排版 → 摘要「最近变化」多一条，父项开放项若无影响则不被打扰。"
            ),
            outcomes=[
                "回答「进展/还差什么/下一步」用列表式短句，不用长篇复述",
                "每条开放项可点证据",
                "大事项树局部更新，响应快",
                "摘要与用户看到的表格下一步一致",
                "可「刷新摘要」但默认不必手动",
            ],
            failures=[
                "答非所问的长作文，找不到下一步",
                "开放项凭空出现或过期不消",
                "改一行字等很久「全文重写」",
                "摘要与表中状态矛盾",
                "只有文采没有证据",
            ],
            constraints=[
                "Capsule 结构固定：Goal/Current/Recent/Open/Files/Evidence",
                "增量优先；全量重写仅 repair 任务",
                "开放项变更必须跟状态机/子项同步，避免残留",
                "摘要禁止添加 Source 之外新事实",
                "面向用户的「当前摘要」与 AI Capsule 同源",
            ],
            custom={
                "responsibilities": ["仪表盘式摘要", "开放项准确", "增量快", "可点证据"],
                "actions": [
                    "update_capsule_incremental",
                    "list_open_items",
                    "propagate_dirty",
                    "sync_with_matter_state",
                ],
                "user_moments": [
                    "开会前 30 秒知道卡点",
                    "改子项不折腾整棵树",
                    "摘要点得进依据",
                ],
                "ux_scorecard": [
                    "首次读懂进展 ≤ 20 秒",
                    "开放项准确率",
                    "局部更新延迟体感「即时」",
                ],
                "in_scope": ["Context Capsule", "Incremental Summary", "Tree Propagation", "Dirty Tracking"],
                "out_of_scope": ["最终状态权威", "文件解析"],
                "real_scenarios": [
                    "启动会开放项三连",
                    "领导页改动局部传播",
                ],
            },
        ),
    },
    "memory-fabric": {
        "name": "记忆织物",
        "summary": "越用越顺手：相关旧事更快冒出来；坏掉可降级，绝不会「服务一挂全失忆」。",
        "spec": spec(
            purpose=(
                "用户不感知索引，只感知「找东西快不快、稳不稳」。记忆织物用派生索引加速联想与检索，"
                "Provider 可拔插；任何加速层坏了，核心问答仍靠账本本身。"
                "好用 = 慢慢变灵，而不是黑盒魔法或突然失忆。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】输入「联…框架…」就开始出候选「联通框架合同」，比从零翻表快。"
                "【稳】语义服务超时 → 仍按标题/人物/时间找到合同，只是少一点「你可能还想要」。"
                "【不吵】弱相关「你可能还记得上周咖啡」默认折叠，不抢镜。"
            ),
            outcomes=[
                "联想/补全体感快，且可一键「只是建议」",
                "Provider 故障时核心功能不塌",
                "建议可忽略/纠正，不影响真源",
                "全量重建索引后体验恢复如初",
                "用户可清理派生数据而不丢账本",
            ],
            failures=[
                "语义一挂，问什么都不知道了",
                "错误联想写进正式状态",
                "一堆低质推荐刷屏",
                "「清理缓存」把业务数据也删了",
            ],
            constraints=[
                "派生-only；重建脚本必须存在且定期演练",
                "建议类结果 UI 标明非正式",
                "召回失败降级路径必须默认开启",
                "禁止后台静默改真源",
                "性能目标：常用联想 P95 体感 < 1s（本地缓存）",
            ],
            custom={
                "responsibilities": ["联想加速", "故障降级", "建议不抢权", "可重建"],
                "actions": ["recall", "suggest_search", "degrade_gracefully", "rebuild_indexes"],
                "user_moments": [
                    "打字到一半有候选",
                    "断网/超时仍能查事项",
                    "清缓存不怕丢正事",
                ],
                "ux_scorecard": ["检索体感速度", "降级后可用率", "误写真源 = 0"],
                "in_scope": ["HOT/WARM/COLD/RAW", "Semantic/Relation Index", "Provider", "Background Consolidation"],
                "out_of_scope": ["用户确认策略", "渠道"],
                "real_scenarios": ["模糊检索出候选", "Provider 超时降级到账本检索"],
            },
        ),
    },
    "durable-task-runtime": {
        "name": "持久任务运行时",
        "summary": "提醒真的会来，还能顺延、关闭、补闹；不会「说了要做结果忘了」或被轰炸。",
        "spec": spec(
            purpose=(
                "用户信任「以后」两个字的前提，是到点真的有人来叫。持久任务把承诺变成可管理的闹钟："
                "到点响、响得对、能推迟、能取消、重启不丢。好用的提醒是「恰到好处的打扰」。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】「三天后提醒我跟合同」→ 三天后手机响，卡片上是合同摘要和上次进展；点「顺延两天」即改，"
                "或「完成」回写事项。"
                "【重启】晚上关机，第三天照样提醒。"
                "【不轰炸】同一事项到期只提醒一次；连续失败合并为一条「2 次未送达」。"
            ),
            outcomes=[
                "到期提醒准时/近准时，并带事项上下文",
                "可顺延/改期/完成/取消，动作秒回",
                "进程重启、会话清空后任务仍在",
                "错过提醒可从「已错过」补看补办",
                "与事项下一步联动（提醒完成 → 下一步更新）",
            ],
            failures=[
                "到点没响，用户自己想起来才尴尬",
                "同一提醒响五遍",
                "只能取消不能顺延，很烦",
                "提醒点进去没有背景，不知所指",
                "重启后任务表空了",
            ],
            constraints=[
                "任务持久化 + 触发幂等",
                "提醒文案必须带 matter 标题与下一步",
                "默认去重窗口与合并策略写死在产品规则里",
                "补送/错过状态用户可见",
                "完成/顺延要回写 Matter，不只关通知",
            ],
            custom={
                "responsibilities": ["到点就响", "好管理", "不轰炸", "连事项"],
                "actions": [
                    "schedule_reminder",
                    "snooze",
                    "complete_reminder",
                    "catch_up_missed",
                    "run_due_tasks",
                ],
                "user_moments": [
                    "三天后准时响起",
                    "会议中顺延到晚上",
                    "重启电脑后仍提醒",
                ],
                "ux_scorecard": [
                    "准时提醒率",
                    "误轰炸投诉 = 0",
                    "提醒→事项状态同步率",
                ],
                "in_scope": ["Reminder", "Delayed/Scheduled Task", "Resume"],
                "out_of_scope": ["是否该创建提醒的语义判断（属运行时/上下文）"],
                "real_scenarios": [
                    "合同三日提醒",
                    "顺延两日",
                    "重启后触发",
                ],
            },
        ),
    },
    "capability-registry": {
        "name": "能力注册表",
        "summary": "能做的立刻能用，不能做的明说不能用；危险操作永远有锁，而不是「看起来像会了」。",
        "spec": spec(
            purpose=(
                "对用户，能力边界要清晰：说「帮我读 PDF」就有反馈——要么读完，要么「当前还没接 PDF」。"
                "注册表把工具变成可预期的按钮，而不是模型即兴发挥；权限让危险键有安全盖。"
            ),
            kind="user_journey",
            narrative=(
                "【好用】「把 PDF 资费存进知识库」→ 进度 → 完成摘要；若 PDF 能力未装：「还不能读 PDF，你可以粘贴文字，"
                "或我帮你记『待安装 PDF 能力』。」"
                "【危险】「把这封信发给王总」→ 预览收件人/正文再发。"
                "【替换】背后换 OCR 引擎，用户只会觉得识别更准，流程不变。"
            ),
            outcomes=[
                "能力可用/不可用反馈明确，不假装",
                "高副作用动作有预览/确认",
                "工具错误人类可读（缺权限/缺文件）",
                "新能力上线后无需用户重新学一套话术",
                "可列出「拾光现在会什么」帮助页",
            ],
            failures=[
                "模型说办好了实际调用失败",
                "未接入能力被幻觉执行",
                "高风险工具被误触",
                "错误信息只有 stack trace",
            ],
            constraints=[
                "未注册/未授权 = 明确失败，禁止幻觉成功",
                "副作用等级强制：external/high-risk 必须确认",
                "用户可见帮助只暴露能力名与示例，不暴露 SDK",
                "废弃能力要提示替代路径",
            ],
            custom={
                "responsibilities": ["能用/不能用说清", "危险有锁", "错误可读", "会什么可查"],
                "actions": ["list_capabilities", "invoke_tool", "preview_high_risk", "explain_failure"],
                "user_moments": ["问能不能读 PDF 立刻知道", "发信前看到预览"],
                "ux_scorecard": ["幻觉成功 = 0", "高风险误触 = 0", "错误可理解率"],
                "in_scope": ["Native Tools", "MCP", "External Service", "Permission"],
                "out_of_scope": ["账本字段语义"],
                "real_scenarios": ["未装 PDF 明确降级", "发信预览", "能力清单"],
            },
        ),
    },
    "projection-layer": {
        "name": "投影层",
        "summary": "多维表格像你自己的工作台：筛得到、改得动、看得懂层级和证据；换工具不换真相。",
        "spec": spec(
            purpose=(
                "用户透过表格建立信任。好用的投影：一眼扫状态，点开子事项，改完就生效，AI 也同步知道。"
                "它不是另一套数据，而是账本的驾驶舱；WPS/Web 可换，驾驶习惯留在语义层。"
            ),
            kind="expected_visual_result",
            narrative=(
                "【视觉/操作】视图「我的事项」默认按下一步日期排序：列=事项|状态|下一步|负责人|更新。"
                "展开春促 → 子事项缩进 + 附件角标。把状态「等待」拖成「完成」→ 立即出现变更提示「已记入账本」。"
                "【不好用】列名与 AI 说的不一致；改单元格没有反馈；子事项只能靠搜索。"
            ),
            outcomes=[
                "默认视图就能回答「我现在有什么事、下一步」",
                "单元格/行操作后 1 秒内有「已保存」反馈",
                "可筛选状态/负责人/时间，排序稳定",
                "子事项层级可展开，附件可点",
                "证据链接与摘要入口在行内直达",
            ],
            failures=[
                "表好看但改了不生效",
                "AI 改了表没刷新，用户覆盖回去",
                "只有平铺长列表，项目组看不到树",
                "离开 WPS 数据就没了",
                "字段含义靠猜",
            ],
            constraints=[
                "默认视图配置产品化（不是用户从零搭）",
                "所有编辑走 State/Commit，带变更回执",
                "冲突：外部改动 vs AI 改动要可见合并，不静默覆盖",
                "字段中文名/英文 ID 映射表随版本发布",
                "只读模式也要能导出当前真相",
            ],
            custom={
                "responsibilities": ["驾驶舱默认视图", "编辑即时回写", "层级/证据可达", "产品可换"],
                "actions": [
                    "render_default_my_matters",
                    "apply_cell_edit",
                    "expand_children",
                    "open_evidence",
                    "sync_after_ai_update",
                ],
                "user_moments": [
                    "打开表就完成今日规划",
                    "拖状态 AI 立刻知道",
                    "开会投屏看子项",
                ],
                "ux_scorecard": [
                    "首次配置时间 ≈ 0（用默认视图）",
                    "编辑回写延迟",
                    "人机状态一致率",
                ],
                "in_scope": ["WPS/多维表", "Web", "Future App"],
                "out_of_scope": ["Canonical 存储"],
                "real_scenarios": [
                    "默认「我的事项」视图",
                    "改状态回写 + 回执",
                    "展开子事项与附件",
                ],
            },
        ),
    },
    "operations": {
        "name": "运维与配置",
        "summary": "换模型、备份、恢复都像改设置而不是搞工程；出问题能定位，不靠玄学。",
        "spec": spec(
            purpose=(
                "长期产品要让人「敢依赖」。运维与配置把恢复和换模做成常规操作：备份有说明、恢复有预检、"
                "换 Provider 有测试、故障有轨迹。用户不必成为工程师也能把拾光从坑里拉回来。"
            ),
            kind="user_journey",
            narrative=(
                "【换模】设置里切换 DeepSeek/本地模型 → 「测试连接」→ 成功继续用，账本零迁移。"
                "【备份】一键导出账本+原文；恢复向导显示「将恢复 128 事项 / 40 附件」，确认后完成。"
                "【排障】提醒没来 → 诊断页显示「任务创建成功但渠道失败 2 次」并给重试。"
            ),
            outcomes=[
                "换模型/Key 不改业务数据，有连通测试",
                "备份/恢复有预览与进度，恢复含 Source",
                "常见故障有自检清单（身份/generation/缓存/渠道）",
                "密钥不明文出现在日志/导出",
                "升级迁移有前后对照",
            ],
            failures=[
                "换模型要停机导库",
                "备份文件恢复不了",
                "用户不知道昨晚为何没提醒",
                "导出包里带着 API Key",
            ],
            constraints=[
                "备份必含 Canonical + Source；Derived 可选",
                "恢复前预检空间/版本/身份",
                "诊断输出脱敏",
                "配置变更与数据迁移分离",
            ],
            custom={
                "responsibilities": ["可换模", "可备份恢复", "可定位", "密钥安全"],
                "actions": ["test_model_provider", "export_backup", "restore_with_preview", "self_diagnose"],
                "user_moments": ["设置里换模型", "一键备份搬家", "自查为何没提醒"],
                "ux_scorecard": ["恢复演练成功率", "换模不迁数据", "敏感信息泄漏 = 0"],
                "in_scope": ["Diagnostics", "Trace", "Backup", "Migration", "Model/Provider Config"],
                "out_of_scope": ["日常记账"],
                "real_scenarios": ["切换模型连通测试", "备份预览恢复", "提醒失败诊断"],
            },
        ),
    },
}


def main():
    print("start_gen", status_gen())
    for mid, data in MODULES.items():
        s1, _ = write(
            "PATCH",
            f"/api/modules/{mid}",
            lambda g: {
                "name": data["name"],
                "project_id": PID,
                "expected_generation": g,
                **ACTOR,
            },
        )
        s2, _ = write(
            "PUT",
            f"/api/modules/{mid}/summary",
            lambda g, t=data["summary"]: {
                "text": t,
                "project_id": PID,
                "expected_generation": g,
                **ACTOR,
            },
        )
        s3, b3 = write(
            "POST",
            f"/api/modules/{mid}/spec",
            lambda g: {
                "project_id": PID,
                "expected_generation": g,
                "base_revision": 2,
                "spec": data["spec"],
                **ACTOR,
            },
        )
        # if base_revision 2 fails for some, try 1
        if s3 >= 300:
            s3, b3 = write(
                "POST",
                f"/api/modules/{mid}/spec",
                lambda g: {
                    "project_id": PID,
                    "expected_generation": g,
                    "base_revision": 1,
                    "spec": data["spec"],
                    **ACTOR,
                },
            )
        print(mid, "rename", s1, "summary", s2, "spec", s3)
        if s3 >= 300:
            print("  ", b3 if isinstance(b3, str) else json.dumps(b3, ensure_ascii=False)[:300])
    print("end_gen", status_gen())


if __name__ == "__main__":
    main()
