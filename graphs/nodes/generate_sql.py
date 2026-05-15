"""
SQL Generation Node for NL2SQL system.
Uses prompt engineering to generate SQL from natural language.
Enhanced with smart schema matching.
Enhanced with multi-table JOIN path generation.
将自然语言转化为sql
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
from tools.schema_manager import schema_manager  # 新增 Schema Manager
from graphs.utils.performance import monitor_performance

def load_prompt_template(template_name: str) -> str:
    """
    Load prompt template from prompts/ directory.

    Args:
        template_name: Name of the template file (without extension)

    Returns:
        Template content as string
    """
    template_path = Path(__file__).parent.parent.parent / "prompts" / f"{template_name}.txt"

    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_sql_from_response(response: str) -> tuple:
    """
    Extract SQL from LLM response.
    Handles various response formats (with/without markdown code blocks).
    增强检测，区分SQL查询和聊天回复

    Args:
        response: LLM response text

    Returns:
        Tuple of (extracted_sql, is_valid_sql)
        - extracted_sql: Extracted SQL statement or original response
        - is_valid_sql: Whether the extracted content is a valid SQL statement
    """
    import re
    
    # Remove markdown code blocks
    if "```sql" in response:
        # Extract content between ```sql and ```
        start = response.find("```sql") + 6
        end = response.find("```", start)
        sql = response[start:end].strip()
    elif "```" in response:
        # Extract content between ``` and ```
        start = response.find("```") + 3
        end = response.find("```", start)
        sql = response[start:end].strip()
    else:
        # No code blocks, use the entire response
        sql = response.strip()

    # Clean up
    sql = sql.strip()

    # 检查是否是有效的SQL语句
    # 检查是否包含SQL关键字（SELECT, FROM等）
    sql_lower = sql.lower()
    sql_keywords = ['select', 'from', 'where', 'join', 'group', 'order', 'having', 'limit']
    has_sql_keywords = any(keyword in sql_lower for keyword in sql_keywords)
    
    # 检查是否看起来像SQL（包含SELECT和FROM）
    is_valid_sql = has_sql_keywords and 'select' in sql_lower and 'from' in sql_lower
    
    # 如果包含明显的聊天内容标识（中文回复、问候语等），不是SQL
    chat_indicators = [
        '你好', '您好', '请问', '请提供', '想要查询', '我可以', '帮助',
        'hello', 'hi', 'how can i', 'i can help', 'please provide',
        '无法', '不能', '抱歉', '对不起', 'sorry', 'cannot', 'unable'
    ]
    has_chat_indicators = any(indicator in sql for indicator in chat_indicators)
    
    if has_chat_indicators or not is_valid_sql:
        # 这是聊天回复，不是SQL
        return response.strip(), False

    # Ensure SQL ends with semicolon
    if not sql.endswith(";"):
        sql += ";"

    return sql, True


def get_database_schema(question: str = "") -> str:
    """
    获取数据库 schema，支持智能匹配
    
    Args:
        question: 用户问题（用于智能匹配相关表）
        
    Returns:
        格式化的 schema 文本
    """
    if question:
        # 智能模式：根据问题返回相关的 schema
        return schema_manager.get_smart_schema_for_question(question)
    else:
        # 完整模式：返回所有 schema
        return schema_manager.format_schema_for_prompt()


def detect_user_intent(question: str) -> tuple:
    """
    使用LLM判断用户意图是聊天还是数据查询
    
    Args:
        question: 用户问题
        
    Returns:
        Tuple of (is_chat, reason)
        - is_chat: True if it's a chat question, False if it's a SQL query
        - reason: Brief reason for the decision
    """
    # 使用模块级别的llm_client（已在文件顶部导入）
    
    intent_prompt = f"""请判断以下用户输入的意图：

用户输入："{question}"

请判断用户的意图是：
1. **聊天对话**：问候、自我介绍、询问系统功能、非数据查询类问题等
2. **数据查询**：需要从数据库中查询、统计、分析数据的问题

请只回答 "CHAT" 或 "QUERY"，不要有其他内容。

如果用户是在：
- 打招呼、问候、自我介绍
- 询问系统如何使用
- 询问系统功能
- 非数据相关的对话
回答：CHAT

如果用户是在：
- 查询数据（如"查询所有客户"）
- 统计数据（如"统计订单数量"）
- 分析数据（如"销售额最高的客户"）
- 需要从数据库获取信息
回答：QUERY

判断结果："""
    
    try:
        # llm_client
        response = llm_client.chat(
            prompt=intent_prompt,
            system_message="你是一个意图识别助手，专门判断用户是想聊天还是查询数据。只回答CHAT或QUERY。"
        )
        
        response_clean = response.strip().upper()
        
        if "CHAT" in response_clean:
            return True, "LLM判断为聊天意图"
        elif "QUERY" in response_clean:
            return False, "LLM判断为数据查询意图"
        else:
            # 如果LLM返回了意外内容，默认判断为查询（保守策略）
            print(f"⚠️  LLM返回了意外的意图判断结果: {response_clean}，默认视为查询")
            return False, "无法判断，默认视为查询"
            
    except Exception as e:
        print(f"⚠️  意图识别失败: {e}，默认视为查询")
        # 如果LLM调用失败，默认视为查询（保守策略）
        return False, f"意图识别失败: {str(e)}"


@monitor_performance
def generate_sql_node(state: NL2SQLState) -> NL2SQLState:
    """
    Generate SQL from natural language question using LLM.
    Now uses smart schema matching based on question.
    Supports regeneration with critique feedback.
    Enhanced with multi-table JOIN path generation.
    Detects chat questions and handles them separately.
    Now uses context memory for better SQL generation.
    """
    question = state.get("question", "")
    critique = state.get("critique")  # Get critique if available
    regeneration_count = state.get("regeneration_count", 0)  #  Track retries
    session_id = state.get("session_id")

    print(f"\n=== Generate SQL Node  ===")
    print(f"Question: {question}")
    
    #获取上下文记忆管理器
    from graphs.utils.context_memory import get_context_manager
    context_manager = get_context_manager(session_id) if session_id else None

    #使用LLM判断用户意图，如果是聊天问题，直接使用通用聊天接口
    if not critique:
        is_chat, reason = detect_user_intent(question)
        print(f" 意图识别: {reason}")
        
        if is_chat:
            print(" 检测到聊天意图，使用通用聊天接口（不使用SQL生成模板）")
            
            #先添加用户问题到历史（在生成响应之前）
            if context_manager and regeneration_count == 0:
                context_manager.add_query(question)
            
            # 格式化历史上下文用于聊天响应
            context_text = ""
            if context_manager:
                context_text = context_manager.format_context_for_sql_generation(question, max_rounds=5)
                if context_text:
                    print(" 已加载历史上下文用于聊天响应")
            
            # 加载聊天提示词，赋予NL2SQL助手身份
            chat_prompt_template = load_prompt_template("chat")
            chat_prompt = chat_prompt_template.format(
                question=question,
                context_history=context_text if context_text else ""
            )
            
            # 使用模块级别的llm_client（已在文件顶部导入），使用NL2SQL助手身份
            chat_response = llm_client.chat(
                prompt=chat_prompt,
                system_message="你是一个NL2SQL助手，专门帮助用户通过自然语言查询数据库内容。"
            )
            
            print(f"Chat Response: {chat_response}")
            
            #添加聊天响应到上下文记忆
            if context_manager:
                context_manager.add_chat_response(chat_response)
            
            return {
                **state,
                "candidate_sql": None,
                "is_chat_response": True,
                "chat_response": chat_response,
                "sql_generated_at": datetime.now().isoformat(),
                "regeneration_count": 0,
                "critique": None,
                "dialog_history": context_manager.get_all_history() if context_manager else state.get("dialog_history", [])
            }
        else:
            print(" 检测到数据查询意图，继续使用SQL生成流程")
            
            #添加查询到上下文记忆（仅在首次生成时，不是重新生成）
            if context_manager and regeneration_count == 0:
                context_manager.add_query(question)

    if critique:
        print(f"Regeneration attempt: {regeneration_count + 1}")
        print(f"Using critique feedback for improvement")
    
    # Load prompt template (only for SQL queries)
    prompt_template = load_prompt_template("nl2sql")

    # 使用智能 schema（根据问题匹配相关表）
    real_schema = get_database_schema(question)
    
    # 打印匹配到的表信息
    relevant_tables = schema_manager.find_relevant_tables(question)
    if relevant_tables:
        print(f"Relevant tables: {', '.join(relevant_tables)}")
    
    # 检测多表查询并生成JOIN路径建议
    join_suggestions = ""
    if relevant_tables and len(relevant_tables) >= 2:
        print(f"Detected multi-table query ({len(relevant_tables)} tables)")
        join_suggestions = schema_manager.format_join_suggestions(relevant_tables)
        if join_suggestions:
            print(" Generated JOIN path suggestions")
            # 打印JOIN路径摘要
            join_steps = schema_manager.find_join_path(relevant_tables)
            if join_steps:
                print(f"  JOIN steps: {len(join_steps)}")
                for i, step in enumerate(join_steps, 1):
                    print(f"    {i}. {step['join_type']} JOIN {step['join_table']} ON {step['condition']}")

    # 格式化历史上下文
    context_text = ""
    if context_manager and not critique:
        context_text = context_manager.format_context_for_sql_generation(question)
        if context_text:
            print("已加载历史上下文用于SQL生成")

    # If this is a regeneration, modify the prompt to include critique
    if critique:
        # Add critique section to prompt
        prompt_with_critique = f"""{prompt_template}

## 重要：之前的 SQL 有错误，请根据以下反馈修复

### 错误分析
{critique}

### 要求
请仔细阅读上述错误分析，生成一个语法正确、符合数据库 schema 的 SQL 查询。
确保：
1. SQL 语法完全正确
2. 表名和字段名与 Schema 完全匹配（区分大小写）
3. 修复所有报告的错误
"""
        # Add JOIN suggestions if available
        if join_suggestions:
            prompt_with_critique = f"""{prompt_with_critique}

{join_suggestions}
"""
        # 添加历史上下文到prompt
        if context_text:
            prompt_with_critique = f"""{prompt_with_critique}

{context_text}
"""
        prompt = prompt_with_critique.format(
            schema=real_schema,
            question=question,
            context_history=context_text if context_text else ""
        )
    else:
        if join_suggestions:
            # Insert JOIN suggestions before the user question
            prompt_template_with_join = prompt_template.replace(
                "## 用户问题",
                f"{join_suggestions}\n\n## 用户问题"
            )
            prompt = prompt_template_with_join.format(
                schema=real_schema,
                question=question,
                context_history=context_text if context_text else ""
            )
        else:
            prompt = prompt_template.format(
                schema=real_schema,
                question=question,
                context_history=context_text if context_text else ""
            )

    try:
        # Call LLM
        response = llm_client.chat(prompt=prompt)

        print(f"\nLLM Response:\n{response}")

        # Extract SQL from response - 现在返回SQL和有效性标志
        candidate_sql, is_valid_sql = extract_sql_from_response(response)

        print(f"\nExtracted SQL:\n{candidate_sql}")
        print(f"Is Valid SQL: {is_valid_sql}")
        
        # 如果不是有效的SQL，说明LLM返回的是聊天回复
        if not is_valid_sql:
            print(" LLM返回的是聊天回复，不是SQL查询")
            # 将LLM的回复作为答案，跳过SQL执行流程
            return {
                **state,
                "candidate_sql": None,  # 没有SQL
                "is_chat_response": True,  # 标记为聊天响应
                "chat_response": candidate_sql,  # 保存聊天回复
                "sql_generated_at": datetime.now().isoformat(),
                "regeneration_count": regeneration_count if critique else 0,
                "critique": None
            }
        
        # Increment regeneration count if this is a retry
        new_regeneration_count = regeneration_count + 1 if critique else 0

        return {
            **state,
            "candidate_sql": candidate_sql,
            "is_chat_response": False,  # 标记为SQL查询
            "chat_response": None,
            "sql_generated_at": datetime.now().isoformat(),
            "regeneration_count": new_regeneration_count,  #  Track retries
            "critique": None,  # Clear critique after using it
            "dialog_history": context_manager.get_all_history() if context_manager else state.get("dialog_history", [])
        }

    except Exception as e:
        print(f"\n✗ Error generating SQL: {e}")

        return {
            **state,
            "candidate_sql": None,
            "is_chat_response": False,
            "chat_response": None,
            "sql_generated_at": datetime.now().isoformat()
        }

