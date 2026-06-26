#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
维权宝 - AI 智能分析引擎
支持 OpenAI API（主）+ 规则引擎（兜底）
"""
import os, json, re, logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─── 配置 ──────────────────────────────────────────────────

AI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
AI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def configure(api_key: str = "", api_base: str = "", model: str = ""):
    """运行时配置 AI 参数"""
    global AI_API_KEY, AI_API_BASE, AI_MODEL
    if api_key:
        AI_API_KEY = api_key
    if api_base:
        AI_API_BASE = api_base
    if model:
        AI_MODEL = model


def is_ai_available() -> bool:
    """检查 AI 是否可用"""
    return bool(AI_API_KEY)


# ─── 主入口 ──────────────────────────────────────────────────

def analyze(conversation: str, messages_text: str, platform: str = "") -> dict:
    """
    智能分析聊天记录，返回结构化结果。

    返回格式:
    {
        "method": "ai" | "rule",
        "case_type": str,           # 案件类型
        "case_type_confidence": float,  # 置信度 0-1
        "summary": str,             # 案情摘要
        "parties": [...],           # 当事人
        "timeline": [...],          # 时间线
        "key_facts": [...],         # 关键事实
        "evidence": {               # 证据分析
            "strength": str,        # 强/中/弱
            "items": [...],         # 证据清单
            "gaps": [...]           # 证据缺口
        },
        "legal_basis": [...],       # 法律依据
        "compensation": str,        # 赔偿/补偿预期
        "action_plan": [...],       # 维权步骤
        "risks": [...],             # 风险提示
        "raw_report": str           # 原始 Markdown 报告（兼容旧版）
    }
    """
    if is_ai_available():
        try:
            return _analyze_with_ai(conversation, messages_text, platform)
        except Exception as e:
            logger.warning(f"AI 分析失败，回退到规则引擎: {e}")

    return _analyze_with_rules(conversation, messages_text)


# ─── OpenAI API 分析 ──────────────────────────────────────────────────

def _analyze_with_ai(conversation: str, messages_text: str, platform: str) -> dict:
    """调用 OpenAI API 进行智能分析"""
    import urllib.request
    import ssl

    prompt = f"""你是一个专业的法律维权助手。请分析以下聊天记录，提取维权要素。

【会话名称】{conversation}
【来源平台】{platform or '未知'}

【聊天记录】
{messages_text[:8000]}

请严格按以下 JSON 格式返回分析结果（不要返回其他内容）：
{{
    "case_type": "案件类型（劳动纠纷/消费维权/合同纠纷/债务纠纷/房屋租赁/交通事故/其他）",
    "case_type_confidence": 0.0到1.0的置信度,
    "summary": "用2-3句话概括案情核心",
    "parties": [
        {{"name": "当事人名称/称呼", "role": "角色（受害者/侵权方/第三方）", "description": "简要描述"}}
    ],
    "timeline": [
        {{"date": "日期（尽量从消息中提取）", "event": "发生了什么事", "importance": "high/medium/low"}}
    ],
    "key_facts": [
        {{"fact": "关键事实描述", "evidence_ref": "对应的聊天内容摘录", "importance": "high/medium/low"}}
    ],
    "evidence": {{
        "strength": "强/中/弱",
        "items": [
            {{"type": "证据类型（聊天记录/转账记录/合同/照片等）", "description": "证据描述", "location": "在聊天记录中的位置"}}
        ],
        "gaps": ["缺少的证据1", "缺少的证据2"]
    }},
    "legal_basis": [
        {{"law": "法律名称", "article": "具体条款", "relevance": "与本案的关联说明"}}
    ],
    "compensation": "可能获得的赔偿/补偿范围和计算依据",
    "action_plan": [
        {{"step": 1, "action": "具体行动", "detail": "操作说明", "deadline": "时效/截止时间", "cost": "预计成本"}}
    ],
    "risks": ["风险1", "风险2"]
}}"""

    body = json.dumps({
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "你是专业的法律维权分析助手，擅长从聊天记录中提取法律要素。只返回 JSON，不要返回其他内容。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_API_KEY}",
    }

    req = urllib.request.Request(
        f"{AI_API_BASE}/chat/completions",
        data=body,
        headers=headers,
        method="POST",
    )

    # 允许自签名证书
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["choices"][0]["message"]["content"]

    # 提取 JSON（可能被 ```json 包裹）
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
    if json_match:
        content = json_match.group(1)
    content = content.strip()

    result = json.loads(content)
    result["method"] = "ai"
    result["raw_report"] = _generate_markdown_report(result)
    return result


# ─── 规则引擎分析（兜底）──────────────────────────────────────────────

# 案件类型关键词配置
CASE_TYPES = {
    "劳动纠纷": {
        "keywords": ['工资', '加班', '辞退', '离职', '社保', '公积金', '劳动合同', '赔偿', '补偿',
                     'N+1', '年终奖', '绩效', '考勤', '开除', '裁员', '降薪', '调岗', '试用期',
                     '五险一金', '带薪年假', '产假', '工伤', '竞业限制', '拖欠工资', '克扣'],
        "laws": [
            {"law": "中华人民共和国劳动合同法", "article": "相关条款"},
            {"law": "中华人民共和国劳动法", "article": "相关条款"},
            {"law": "劳动争议调解仲裁法", "article": "相关条款"},
        ],
        "action_template": [
            {"step": 1, "action": "收集证据", "detail": "保存劳动合同、工资条、考勤记录、聊天记录截图"},
            {"step": 2, "action": "向劳动监察大队投诉", "detail": "拨打 12333 或到当地劳动监察大队现场投诉", "cost": "免费"},
            {"step": 3, "action": "申请劳动仲裁", "detail": "向劳动人事争议仲裁委员会提交仲裁申请", "deadline": "知道权利被侵害之日起1年内", "cost": "免费"},
            {"step": 4, "action": "向法院起诉", "detail": "对仲裁结果不服可在收到裁决书之日起15日内向法院起诉", "cost": "诉讼费10元"},
        ],
    },
    "消费维权": {
        "keywords": ['退款', '退货', '假货', '质量问题', '售后', '投诉', '欺诈', '虚假宣传',
                     '霸王条款', '三包', '翻新', '以次充好', '过期', '变质', '假冒', '伪劣',
                     '消费者', '购物', '购买', '商家', '客服', '差评'],
        "laws": [
            {"law": "中华人民共和国消费者权益保护法", "article": "相关条款"},
            {"law": "中华人民共和国产品质量法", "article": "相关条款"},
            {"law": "中华人民共和国食品安全法", "article": "相关条款"},
        ],
        "action_template": [
            {"step": 1, "action": "保留证据", "detail": "保存购买凭证、订单截图、商品照片、聊天记录"},
            {"step": 2, "action": "与商家协商", "detail": "先联系商家客服协商退款/赔偿"},
            {"step": 3, "action": "向12315投诉", "detail": "拨打12315或登录全国12315平台投诉", "cost": "免费"},
            {"step": 4, "action": "向消费者协会投诉", "detail": "请求消费者协会调解", "cost": "免费"},
            {"step": 5, "action": "向法院起诉", "detail": "欺诈行为可主张退一赔三（最低500元）", "cost": "诉讼费按标的额计算"},
        ],
    },
    "合同纠纷": {
        "keywords": ['合同', '违约', '定金', '订金', '违约金', '解除', '履行', '纠纷',
                     '签约', '甲方', '乙方', '条款', '协议', '约定', '违约责任', '解除合同',
                     '终止', '续签', '变更'],
        "laws": [
            {"law": "中华人民共和国民法典", "article": "合同编"},
        ],
        "action_template": [
            {"step": 1, "action": "整理合同文件", "detail": "收集合同原件、补充协议、往来函件"},
            {"step": 2, "action": "协商解决", "detail": "与对方协商变更或解除合同"},
            {"step": 3, "action": "申请调解", "detail": "向人民调解委员会申请调解", "cost": "免费"},
            {"step": 4, "action": "申请仲裁或起诉", "detail": "根据合同约定选择仲裁或诉讼", "cost": "按标的额计算"},
        ],
    },
    "债务纠纷": {
        "keywords": ['欠款', '借款', '还款', '利息', '借条', '欠条', '催收', '逾期',
                     '本金', '月息', '年息', '高利贷', '套路贷', '担保', '抵押', '连带'],
        "laws": [
            {"law": "中华人民共和国民法典", "article": "合同编"},
            {"law": "最高人民法院关于审理民间借贷案件适用法律若干问题的规定", "article": "相关条款"},
        ],
        "action_template": [
            {"step": 1, "action": "固定债权凭证", "detail": "保存借条、转账记录、催款记录"},
            {"step": 2, "action": "协商还款", "detail": "与债务人协商还款计划"},
            {"step": 3, "action": "申请支付令", "detail": "向法院申请支付令（快速、低成本）", "cost": "诉讼费的1/3"},
            {"step": 4, "action": "起诉并申请财产保全", "detail": "向法院起诉，同时申请冻结对方财产", "cost": "按标的额计算"},
        ],
    },
    "房屋租赁": {
        "keywords": ['房租', '押金', '水电', '物业', '维修', '漏水', '甲醛', '退租',
                     '房东', '中介', '租金', '转租', '合租', '装修', '家具', '家电',
                     '门锁', '钥匙', '到期'],
        "laws": [
            {"law": "中华人民共和国民法典", "article": "合同编·租赁合同章"},
            {"law": "商品房屋租赁管理办法", "article": "相关条款"},
        ],
        "action_template": [
            {"step": 1, "action": "保留租赁证据", "detail": "保存租赁合同、押金收据、房屋照片、沟通记录"},
            {"step": 2, "action": "与房东/中介协商", "detail": "书面（微信/邮件）沟通，留下证据"},
            {"step": 3, "action": "向住建部门投诉", "detail": "向当地住房和城乡建设局投诉", "cost": "免费"},
            {"step": 4, "action": "向法院起诉", "detail": "向房屋所在地基层法院起诉", "cost": "诉讼费按标的额计算"},
        ],
    },
    "交通事故": {
        "keywords": ['事故', '责任', '保险', '定损', '维修费', '误工费', '医疗费',
                     '交警', '事故认定', '全责', '主责', '次责', '同等责任', '肇事',
                     '逃逸', '酒驾', '醉驾', '伤残', '鉴定'],
        "laws": [
            {"law": "中华人民共和国道路交通安全法", "article": "相关条款"},
            {"law": "机动车交通事故责任强制保险条例", "article": "相关条款"},
            {"law": "最高人民法院关于审理人身损害赔偿案件适用法律若干问题的解释", "article": "相关条款"},
        ],
        "action_template": [
            {"step": 1, "action": "保留事故证据", "detail": "保存事故认定书、现场照片、医疗记录、费用发票"},
            {"step": 2, "action": "保险理赔", "detail": "向对方保险公司或自己的保险公司报案理赔"},
            {"step": 3, "action": "协商赔偿", "detail": "与对方协商赔偿金额"},
            {"step": 4, "action": "向法院起诉", "detail": "协商不成向事故发生地或被告住所地法院起诉", "cost": "诉讼费按标的额计算"},
        ],
    },
}


def _count_keywords(text: str, keywords: list) -> dict:
    """统计关键词出现次数"""
    return {kw: text.count(kw) for kw in keywords if text.count(kw) > 0}


def _extract_dates(text: str) -> list:
    """从文本中提取日期"""
    dates = []
    # 匹配 2024年1月1日, 2024-01-01, 2024/1/1, 1月1日 等
    patterns = [
        r'(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日号]?',
        r'(\d{1,2})[月\-/](\d{1,2})[日号]?',
    ]
    for p in patterns:
        for m in re.finditer(p, text):
            dates.append(m.group(0))
    return list(set(dates))


def _extract_amounts(text: str) -> list:
    """从文本中提取金额"""
    amounts = []
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:万|千|百)?元',
        r'[￥¥]\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*(?:块钱|元整)',
    ]
    for p in patterns:
        for m in re.finditer(p, text):
            amounts.append(m.group(0))
    return list(set(amounts))


def _extract_parties(text: str, conversation: str) -> list:
    """提取当事人（简单启发式）"""
    parties = []
    # 从发送者中提取
    senders = re.findall(r'\]\s*(.+?):', text)
    unique_senders = list(set(senders))[:5]
    for s in unique_senders:
        role = "受害者" if any(w in text.split(s)[-1][:200] for w in ['投诉', '举报', '起诉', '维权']) else "当事方"
        parties.append({"name": s.strip(), "role": role, "description": ""})
    return parties


def _extract_timeline(text: str) -> list:
    """提取简单时间线"""
    timeline = []
    lines = text.split('\n')
    for line in lines:
        date_match = re.search(r'\[(\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}[日号]?\s*\d{1,2}:\d{2}(?::\d{2})?)\]', line)
        if date_match:
            date_str = date_match.group(1)
            content = line.split(']', 2)[-1].strip() if ']' in line else line
            if content and len(content) > 2:
                # 判断重要性
                importance = "low"
                high_words = ['辞退', '开除', '解雇', '欠款', '违约', '赔偿', '起诉', '报警', '仲裁', '投诉']
                if any(w in content for w in high_words):
                    importance = "high"
                elif any(w in content for w in ['工资', '退款', '还款', '合同']):
                    importance = "medium"
                timeline.append({
                    "date": date_str,
                    "event": content[:100],
                    "importance": importance,
                })
    return timeline[-20:]  # 最近20条


def _assess_evidence(text: str, case_type: str) -> dict:
    """评估证据强度"""
    items = []
    gaps = []
    score = 0

    # 检查各类证据
    if re.search(r'转账|汇款|红包|付款|到账', text):
        items.append({"type": "转账记录", "description": "聊天中提及转账/付款", "location": "聊天记录"})
        score += 2
    else:
        gaps.append("缺少转账/付款记录")

    if re.search(r'合同|协议|签字|盖章', text):
        items.append({"type": "合同/协议", "description": "聊天中提及合同或协议", "location": "聊天记录"})
        score += 2
    else:
        gaps.append("缺少书面合同/协议")

    if re.search(r'截图|照片|视频|录音', text):
        items.append({"type": "多媒体证据", "description": "聊天中提及截图/照片/视频", "location": "聊天记录"})
        score += 1

    if re.search(r'承诺|保证|答应|同意|确认', text):
        items.append({"type": "承诺记录", "description": "对方在聊天中做出承诺", "location": "聊天记录"})
        score += 1

    if re.search(r'威胁|恐吓|辱骂|骚扰', text):
        items.append({"type": "侵权行为记录", "description": "聊天中存在威胁/恐吓/辱骂内容", "location": "聊天记录"})
        score += 2

    # 聊天记录本身就是证据
    items.append({"type": "聊天记录", "description": "完整的聊天记录截图", "location": "当前导出"})
    score += 1

    # 评估强度
    if score >= 5:
        strength = "强"
    elif score >= 3:
        strength = "中"
    else:
        strength = "弱"

    return {"strength": strength, "items": items, "gaps": gaps}


def _analyze_with_rules(conversation: str, messages_text: str) -> dict:
    """规则引擎分析"""
    # 1. 匹配案件类型
    type_scores = {}
    for case_type, config in CASE_TYPES.items():
        matches = _count_keywords(messages_text, config["keywords"])
        if matches:
            type_scores[case_type] = {
                "score": sum(matches.values()),
                "matches": matches,
            }

    if not type_scores:
        return {
            "method": "rule",
            "case_type": "未识别",
            "case_type_confidence": 0.0,
            "summary": "未从聊天记录中识别到明确的维权要素。请确认选择了正确的会话，或尝试加载更多消息。",
            "parties": [],
            "timeline": [],
            "key_facts": [],
            "evidence": {"strength": "弱", "items": [], "gaps": ["未识别到有效证据"]},
            "legal_basis": [],
            "compensation": "无法判断",
            "action_plan": [
                {"step": 1, "action": "确认会话", "detail": "确认是否选择了正确的聊天会话"},
                {"step": 2, "action": "加载更多消息", "detail": "点击'加载更多'获取完整聊天记录"},
                {"step": 3, "action": "手动搜索", "detail": "使用搜索功能查找相关关键词"},
            ],
            "risks": ["当前聊天记录中未发现明确的维权要素"],
            "raw_report": "## ⚠️ 未识别到明确的维权要素\n\n当前聊天记录中未发现明显的维权关键词。建议确认是否选择了正确的会话，或尝试加载更多消息。",
        }

    # 按得分排序
    sorted_types = sorted(type_scores.items(), key=lambda x: x[1]["score"], reverse=True)
    main_type = sorted_types[0]
    case_type_name = main_type[0]
    case_config = CASE_TYPES[case_type_name]
    matches = main_type[1]["matches"]

    # 计算置信度（简单：得分越高越自信）
    total_score = sum(v["score"] for v in type_scores.values())
    confidence = round(main_type[1]["score"] / max(total_score, 1), 2)

    # 2. 提取关键信息
    dates = _extract_dates(messages_text)
    amounts = _extract_amounts(messages_text)
    parties = _extract_parties(messages_text, conversation)
    timeline = _extract_timeline(messages_text)
    evidence = _assess_evidence(messages_text, case_type_name)

    # 3. 构建关键事实
    key_facts = []
    for kw, count in sorted(matches.items(), key=lambda x: x[1], reverse=True)[:5]:
        key_facts.append({
            "fact": f"聊天记录中多次提及「{kw}」（共 {count} 次）",
            "evidence_ref": f"关键词: {kw}",
            "importance": "high" if count >= 3 else "medium",
        })
    if amounts:
        key_facts.append({
            "fact": f"涉及金额: {', '.join(amounts[:5])}",
            "evidence_ref": "金额提取",
            "importance": "high",
        })

    # 4. 构建案情摘要
    other_types = ', '.join([t[0] for t in sorted_types[1:3]])
    summary = f"该聊天记录主要涉及「{case_type_name}」"
    if other_types:
        summary += f"，兼涉{other_types}"
    summary += f"。核心关键词出现 {main_type[1]['score']} 次"
    if amounts:
        summary += f"，涉及金额 {amounts[0]}"
    summary += "。"

    # 5. 赔偿预期
    compensation = "需根据具体案情和证据确定"
    if case_type_name == "劳动纠纷":
        if any(w in messages_text for w in ['辞退', '开除', '解雇', '裁员']):
            compensation = "违法解除劳动合同: 2N 赔偿金（N=工作年限×月平均工资）"
        elif '拖欠' in messages_text or '欠薪' in messages_text:
            compensation = "拖欠工资: 全额支付 + 25% 经济补偿金"
    elif case_type_name == "消费维权":
        if any(w in messages_text for w in ['欺诈', '假货', '假冒']):
            compensation = "欺诈行为: 退一赔三（消费金额的3倍，最低500元）"
    elif case_type_name == "债务纠纷":
        if amounts:
            compensation = f"本金 {amounts[0]} + 合法利息（年利率不超过LPR的4倍）"

    # 6. 风险提示
    risks = []
    if evidence["strength"] == "弱":
        risks.append("当前证据较为薄弱，建议补充更多书面证据")
    if not dates:
        risks.append("未能从聊天记录中提取明确的时间节点，建议整理时间线")
    if case_type_name == "劳动纠纷":
        risks.append("劳动仲裁时效为1年，请注意时效问题")
    elif case_type_name == "消费维权":
        risks.append("消费者维权诉讼时效为3年（自知道权益受损之日起）")

    # 7. 生成 Markdown 报告
    result = {
        "method": "rule",
        "case_type": case_type_name,
        "case_type_confidence": confidence,
        "summary": summary,
        "parties": parties,
        "timeline": timeline,
        "key_facts": key_facts,
        "evidence": evidence,
        "legal_basis": case_config["laws"],
        "compensation": compensation,
        "action_plan": case_config["action_template"],
        "risks": risks,
    }
    result["raw_report"] = _generate_markdown_report(result)
    return result


# ─── Markdown 报告生成 ──────────────────────────────────────────────────

def _generate_markdown_report(result: dict) -> str:
    """从结构化结果生成 Markdown 报告"""
    lines = []
    lines.append("## 📋 聊天记录分析报告")
    lines.append("")

    # 案件类型
    conf_pct = int(result.get("case_type_confidence", 0) * 100)
    lines.append(f"### 🎯 案件类型: **{result['case_type']}** （置信度 {conf_pct}%）")
    lines.append("")
    lines.append(f"**案情摘要**: {result.get('summary', '')}")
    lines.append("")

    # 当事人
    parties = result.get("parties", [])
    if parties:
        lines.append("### 👥 当事人")
        lines.append("")
        for p in parties:
            lines.append(f"- **{p['name']}** ({p['role']})")
        lines.append("")

    # 时间线
    timeline = result.get("timeline", [])
    if timeline:
        lines.append("### 📅 时间线")
        lines.append("")
        for t in timeline[-10:]:
            icon = "🔴" if t.get("importance") == "high" else "🟡" if t.get("importance") == "medium" else "⚪"
            lines.append(f"- {icon} **{t['date']}** — {t['event']}")
        lines.append("")

    # 关键事实
    key_facts = result.get("key_facts", [])
    if key_facts:
        lines.append("### 🔍 关键事实")
        lines.append("")
        for f in key_facts:
            icon = "❗" if f.get("importance") == "high" else "📌"
            lines.append(f"- {icon} {f['fact']}")
        lines.append("")

    # 证据分析
    evidence = result.get("evidence", {})
    if evidence:
        strength = evidence.get("strength", "未知")
        strength_icon = "🟢" if strength == "强" else "🟡" if strength == "中" else "🔴"
        lines.append(f"### 📊 证据强度: {strength_icon} {strength}")
        lines.append("")
        for item in evidence.get("items", []):
            lines.append(f"- ✅ [{item['type']}] {item['description']}")
        for gap in evidence.get("gaps", []):
            lines.append(f"- ❌ 缺少: {gap}")
        lines.append("")

    # 法律依据
    legal = result.get("legal_basis", [])
    if legal:
        lines.append("### ⚖️ 法律依据")
        lines.append("")
        for l in legal:
            lines.append(f"- 《{l['law']}》{l.get('article', '')}")
        lines.append("")

    # 赔偿预期
    comp = result.get("compensation", "")
    if comp:
        lines.append("### 💰 赔偿/补偿预期")
        lines.append("")
        lines.append(comp)
        lines.append("")

    # 维权步骤
    actions = result.get("action_plan", [])
    if actions:
        lines.append("### 📝 维权步骤")
        lines.append("")
        for a in actions:
            cost = f"（费用: {a['cost']}）" if a.get('cost') else ""
            deadline = f" ⏰ {a['deadline']}" if a.get('deadline') else ""
            lines.append(f"{a['step']}. **{a['action']}**: {a['detail']}{cost}{deadline}")
        lines.append("")

    # 风险提示
    risks = result.get("risks", [])
    if risks:
        lines.append("### ⚠️ 风险提示")
        lines.append("")
        for r in risks:
            lines.append(f"- {r}")
        lines.append("")

    lines.append("---")
    method = "AI 智能分析" if result.get("method") == "ai" else "规则引擎分析"
    lines.append(f"*本报告由{method}生成，仅供参考。具体维权方案请咨询专业律师*")

    return '\n'.join(lines)
