"""
Dialog Clarification Node for NL2SQL system.
Supports multi-turn dialog and clarification questions.
在生成sql之前看是否存在歧义
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from graphs.state import NL2SQLState
from tools.llm_client import llm_client
from tools.schema_manager import schema_manager
from graphs.utils.performance import monitor_performance


def load_prompt_template(template_name: str) -> str:
    """Load prompt template from prompts/ directory."""
    template_path = Path(__file__).parent.parent.parent / "prompts" / f"{template_name}.txt"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def check_if_needs_clarification(question: str, candidate_sql: Optional[str] = None) -> Dict[str, Any]:
    """
    判断是否需要澄清的判据(修复版v2)

    设计原则:
    1. 默认不澄清,只在真正模糊时才澄清(避免过度澄清)
    2. 任何具体的查询动词+查询对象的组合都视为已明确
    3. 真正需要澄清的场景:疑问代词缺主语、模糊量词缺对象、明确歧义词

    Returns:
        {
            "needs_clarification": bool,
            "reasons": List[str],
            "clarification_type": str
        }
    """
    if not question or not question.strip():
        return {"needs_clarification": False, "reasons": [], "clarification_type": "general"}

    question_stripped = question.strip()
    question_lower = question_stripped.lower()
    reasons = []
    clarification_type = None

    # =================================================================
    # 早期返回:如果是明确的"动词+对象"结构,直接判定为不需要澄清
    # =================================================================

    # 明确的查询动词
    query_verbs = ["查询", "查找", "查一下", "查看", "看一下", "看看",
                   "显示", "列出", "罗列", "给出", "给我", "找出", "找到",
                   "统计", "计算", "求", "算", "数一下",
                   "排序", "排列", "排名"]

    # 明确的实体类词(常见数据库实体的中文描述,不限定于具体数据库)
    common_entities = [
        # 教育领域
        "学生", "学员", "老师", "教师", "课程", "成绩", "分数", "专业", "学院", "学校", "班级",
        # 商业领域
        "客户", "用户", "顾客", "商品", "产品", "货物", "订单", "购买", "销售", "员工", "发票",
        # 图书领域
        "图书", "书", "书籍", "读者", "借阅", "出版社", "作者",
        # 通用属性
        "姓名", "名字", "名称", "标题", "ID", "编号", "日期", "时间", "年份",
        "数量", "总数", "总和", "金额", "价格", "价钱", "总价", "总金额",
        "平均", "最高", "最大", "最多", "最低", "最小", "最少",
        "地址", "电话", "邮箱", "城市", "国家", "性别", "年龄", "状态",
    ]

    has_query_verb = any(v in question_stripped for v in query_verbs)
    has_entity = any(e in question_stripped for e in common_entities)

    # 如果有明确的"查询动词+实体"组合,直接判定为不需要澄清
    if has_query_verb and has_entity:
        return {"needs_clarification": False, "reasons": [], "clarification_type": "general"}

    # 如果是"列出所有X"、"所有X"、"全部X"这种明确格式,也不需要澄清
    if any(p in question_stripped for p in ["所有", "全部", "全体", "整个"]) and has_entity:
        return {"needs_clarification": False, "reasons": [], "clarification_type": "general"}

    # 如果包含明确条件词(大于/小于/等于/在...里),通常不需要澄清
    condition_words = ["大于", "小于", "等于", "高于", "低于", "超过", "不超过",
                       "多于", "少于", "包含", "属于", "在", "不在", "为", "是"]
    has_condition = any(c in question_stripped for c in condition_words)
    if has_condition and has_entity:
        return {"needs_clarification": False, "reasons": [], "clarification_type": "general"}

    # =================================================================
    # 真正需要澄清的判据
    # =================================================================

    # 判据1: 极度模糊的代词或短语(如"那个"、"这种"且没有上下文)
    very_vague_phrases = ["那个", "这个", "那些", "这些", "怎么样", "怎么办", "什么"]
    is_too_short = len(question_stripped) <= 4
    has_vague_only = any(p == question_stripped for p in very_vague_phrases) or \
                     (is_too_short and not has_entity)

    if has_vague_only:
        reasons.append("查询表述过于简短或模糊,缺少明确的查询对象")
        clarification_type = "field"

    # 判据2: 包含主观/定性词汇但没有明确定义
    # 比如"好的学生"、"重要的客户"、"热销的商品"
    subjective_words = ["好的", "差的", "重要的", "主要的", "热销", "畅销",
                        "优秀", "突出", "厉害", "牛", "棒", "强",
                        "成绩好", "成绩差", "厉害的"]
    if any(w in question_stripped for w in subjective_words):
        reasons.append("包含主观/定性词汇,需要明确客观判断标准")
        if not clarification_type:
            clarification_type = "ambiguity"

    # 判据3: "信息"、"情况"、"详情"等极度宽泛的词,且没有任何具体实体
    super_vague = ["情况", "详情", "概况", "状况"]
    if any(w in question_stripped for w in super_vague):
        # 但如果同时指明了具体对象(如"张三的情况"),则不算模糊
        has_specific_target = any(c.isalpha() and c not in common_entities
                                  for c in question_stripped if ord(c) > 127)
        # 简化判断:只要包含人名或具体编号则视为已明确
        if not has_specific_target and not has_entity:
            reasons.append("查询过于宽泛,需要明确具体字段或属性")
            if not clarification_type:
                clarification_type = "field"

    # 判据4: 单纯的数字/年份,没有任何动词或对象(如"2022")
    if question_stripped.isdigit() and len(question_stripped) <= 4:
        reasons.append("仅输入数字,无法判断查询意图")
        if not clarification_type:
            clarification_type = "general"

    # 判据5: "多少"、"几个"等模糊量词,且后面没有跟具体实体
    quantity_words_pattern = ["多少", "几个", "多大", "多高", "多长"]
    for qw in quantity_words_pattern:
        if qw in question_stripped:
            # 检查这个量词后面是否紧跟着具体实体
            idx = question_stripped.index(qw) + len(qw)
            remaining = question_stripped[idx:].strip()
            if not remaining or len(remaining) <= 1:
                reasons.append(f"使用了模糊量词'{qw}'但未明确查询对象")
                if not clarification_type:
                    clarification_type = "aggregation"
                break
            # 如果后面有实体,则视为已明确
            if not any(e in remaining for e in common_entities):
                reasons.append(f"'{qw}'后的对象不够明确")
                if not clarification_type:
                    clarification_type = "aggregation"
                break

    needs_clarification = len(reasons) > 0

    return {
        "needs_clarification": needs_clarification,
        "reasons": reasons,
        "clarification_type": clarification_type or "general"
    }


@monitor_performance
def clarify_node(state: NL2SQLState) -> NL2SQLState:
    """
    澄清节点：判断是否需要澄清，如果需要则生成澄清问题

    使用已有的 dialog_history 字段维护对话历史。
    """
    question = state.get("question", "")
    candidate_sql = state.get("candidate_sql")
    clarification_answer = state.get("clarification_answer")  # 用户对澄清问题的回答
    clarification_count = state.get("clarification_count", 0)
    max_clarifications = state.get("max_clarifications", 3)
    
    #  使用已有的 dialog_history 字段，上下文记忆管理器
    session_id = state.get("session_id")
    from graphs.utils.context_memory import get_context_manager
    context_manager = get_context_manager(session_id) if session_id else None
    
    dialog_history = state.get("dialog_history") or []
    user_id = state.get("user_id")  #  使用已有的 user_id 字段

    print(f"Question: {question}")
    if user_id:
        print(f"User ID: {user_id}")
    print(f"Clarification count: {clarification_count}")
    print(f"Dialog history length: {len(dialog_history)}")
    
    # 如果用户已经回答了澄清问题，更新问题并继续
    if clarification_answer:
        print(f"User answered: {clarification_answer}")
        
        # 更新问题：将澄清信息整合到原问题中
        # 从对话历史中找到原始问题
        original_question = question
        for entry in reversed(dialog_history):
            if entry.get("role") == "user" and entry.get("content"):
                # 移除之前可能添加的澄清信息
                content = entry["content"]
                if "（" in content and "）" in content:
                    original_question = content.split("（")[0]
                else:
                    original_question = content
                break
        
        normalized_question = f"{original_question}（{clarification_answer}）"
        
        # 使用上下文记忆管理器更新对话历史
        if context_manager:
            context_manager.add_clarification_answer(clarification_answer)
            updated_history = context_manager.get_all_history()
        else:
            # 回退到原有逻辑
            updated_history = dialog_history.copy()
            updated_history.append({
                "role": "assistant",
                "content": state.get("clarification_question", ""),
                "timestamp": datetime.now().isoformat(),
                "type": "clarification"
            })
            updated_history.append({
                "role": "user",
                "content": clarification_answer,
                "timestamp": datetime.now().isoformat(),
                "type": "clarification_answer"
            })
        
        return {
            **state,
            "question": normalized_question,  # 更新问题
            "normalized_question": normalized_question,
            "candidate_sql": None,  # 清空旧的SQL，需要重新生成
            "clarification_answer": None,  # 清空回答
            "clarification_question": None,  # 清空澄清问题
            "needs_clarification": False,  # 不再需要澄清
            "dialog_history": updated_history  # 更新对话历史
        }
    
    # 检查是否需要澄清
    clarification_check = check_if_needs_clarification(question, candidate_sql)
    needs_clarification = clarification_check["needs_clarification"]
    
    # 如果超过最大澄清次数，不再澄清
    if clarification_count >= max_clarifications:
        print(f" 已达到最大澄清次数 ({max_clarifications})，跳过澄清")
        needs_clarification = False
    
    if not needs_clarification:
        print(" No clarification needed")
        return {
            **state,
            "needs_clarification": False
        }
    
    # 需要澄清，生成澄清问题
    print(f"  Needs clarification: {clarification_check['reasons']}")
    
    try:
        # 加载澄清prompt模板
        prompt_template = load_prompt_template("clarify")
        
        # 获取schema用于上下文
        schema = schema_manager.get_smart_schema_for_question(question)
        
        # 构建prompt
        reasons_text = "\n".join(f"- {r}" for r in clarification_check["reasons"])
        clarification_type = clarification_check["clarification_type"]
        
        # M9.75: 使用上下文记忆管理器格式化历史上下文
        if context_manager:
            history_text = context_manager.format_context_for_clarification(
                question=question,
                candidate_sql=candidate_sql
            )
        else:
            # 回退到原有逻辑
            history_text = ""
            if dialog_history:
                history_text = "\n## 对话历史\n"
                for entry in dialog_history[-5:]:  # 只取最近5轮
                    role = entry.get("role", "unknown")
                    content = entry.get("content", "")
                    timestamp = entry.get("timestamp", "")
                    history_text += f"[{timestamp}] {role}: {content}\n"
        
        prompt = prompt_template.format(
            question=question,
            schema=schema,
            reasons=reasons_text,
            clarification_type=clarification_type,
            dialog_history=history_text
        )
        
        # 调用LLM生成澄清问题
        response = llm_client.chat(prompt=prompt)
        
        # 解析LLM响应，提取澄清问题和选项
        clarification_question, clarification_options = parse_clarification_response(response)
        
        print(f"\nGenerated clarification question:")
        print(f"  Q: {clarification_question}")
        if clarification_options:
            print(f"  Options:")
            for i, opt in enumerate(clarification_options, 1):
                print(f"    {i}. {opt}")
        
        # M9.75: 使用上下文记忆管理器更新对话历史
        if context_manager:
            context_manager.add_clarification(
                clarification_question=clarification_question,
                options=clarification_options,
                reasons=clarification_check["reasons"]
            )
            updated_history = context_manager.get_all_history()
        else:
            # 回退到原有逻辑
            updated_history = dialog_history.copy()
            updated_history.append({
                "role": "user",
                "content": question,
                "timestamp": datetime.now().isoformat(),
                "type": "question"
            })
            updated_history.append({
                "role": "assistant",
                "content": clarification_question,
                "timestamp": datetime.now().isoformat(),
                "type": "clarification",
                "options": clarification_options
            })
        
        return {
            **state,
            "needs_clarification": True,
            "clarification_question": clarification_question,
            "clarification_options": clarification_options,
            "clarification_count": clarification_count + 1,
            "dialog_history": updated_history  # 更新对话历史
        }
        
    except Exception as e:
        print(f"✗ Error generating clarification: {e}")
        import traceback
        traceback.print_exc()
        # 如果生成澄清问题失败，继续执行（不阻塞流程）
        return {
            **state,
            "needs_clarification": False
        }


def parse_clarification_response(response: str) -> tuple[str, List[str]]:
    """
    解析LLM响应，提取澄清问题和选项
    
    Expected format:
    问题: [澄清问题]
    
    选项:
    1. [选项1]
    2. [选项2]
    3. [选项3]
    
    Returns:
        (clarification_question, clarification_options)
    """
    import re
    
    # 提取问题
    question_match = re.search(r'问题[：:]\s*(.+?)(?:\n|选项|$)', response, re.DOTALL)
    if not question_match:
        # 尝试其他格式
        question_match = re.search(r'澄清问题[：:]\s*(.+?)(?:\n|选项|$)', response, re.DOTALL)
    
    clarification_question = question_match.group(1).strip() if question_match else "请提供更多信息以帮助我理解您的需求。"
    
    # 提取选项
    options = []
    # 匹配编号列表：1. 2. 3. 或 1) 2) 3)
    option_pattern = r'[0-9]+[\.\)、]\s*(.+?)(?:\n|$)'
    option_matches = re.findall(option_pattern, response)
    
    if option_matches:
        options = [opt.strip() for opt in option_matches]
    else:
        # 如果没有找到选项，尝试提取"选项"部分
        options_section = re.search(r'选项[：:]\s*(.+?)(?:\n\n|$)', response, re.DOTALL)
        if options_section:
            # 按行分割并清理
            lines = options_section.group(1).strip().split('\n')
            options = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
    
    # 如果仍然没有选项，至少提供一个默认选项
    if not options:
        options = ["继续执行查询", "取消查询"]
    
    return clarification_question, options


def should_ask_clarification(state: NL2SQLState) -> str:
    """
    条件判断函数：决定是否需要进入澄清流程
    
    Returns:
        "clarify": 需要澄清，输出澄清问题给用户
        "regenerate": 用户已回答，需要重新生成SQL
        "continue": 继续执行（不需要澄清）
    """
    needs_clarification = state.get("needs_clarification", False)
    clarification_answer = state.get("clarification_answer")
    
    # 如果用户已经回答了澄清问题，需要重新生成SQL
    if clarification_answer:
        return "regenerate"
    
    # 如果需要澄清且还没有生成澄清问题，进入澄清
    if needs_clarification and not state.get("clarification_question"):
        return "clarify"
    
    # 其他情况继续执行
    return "continue"

