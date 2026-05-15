"""
测试 Dialog Clarification功能
验证多轮对话与澄清问题功能是否正常工作
测试上下文记忆管理器与澄清功能的集成
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
# 安全修复：test文件在test子目录中，需要使用parent.parent获取项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from graphs.nodes.clarify import (
    check_if_needs_clarification,
    clarify_node,
    parse_clarification_response,
    should_ask_clarification
)
from graphs.state import NL2SQLState
from graphs.base_graph import run_query
from graphs.utils.context_memory import (
    ContextMemoryManager,
    get_context_manager,
    clear_context_manager
)


def test_clarification_criteria():
    """测试澄清判据"""
    print("=" * 60)
    print("测试 1: 澄清判据检查")
    print("=" * 60)
    
    test_cases = [
        {
            "question": "查询最近的发票",
            "should_clarify": True,
            "reason": "缺少具体时间范围"
        },
        {
            "question": "查询最近一个月的发票",
            "should_clarify": False,
            "reason": "时间范围明确"
        },
        {
            "question": "统计客户信息",
            "should_clarify": True,
            "reason": "聚合方式不明确"
        },
        {
            "question": "统计客户总数",
            "should_clarify": False,
            "reason": "聚合方式明确（总数）"
        },
        {
            "question": "查看发票情况",
            "should_clarify": True,
            "reason": "字段需求不明确"
        },
        {
            "question": "查询发票ID和发票日期",
            "should_clarify": False,
            "reason": "字段需求明确"
        },
        {
            "question": "查询最重要的客户",
            "should_clarify": True,
            "reason": "存在歧义词汇（最重要）"
        },
        {
            "question": "查询专辑信息",
            "should_clarify": True,
            "reason": "字段需求不明确"
        },
        {
            "question": "查询专辑名称和艺术家",
            "should_clarify": False,
            "reason": "字段需求明确"
        },
        {
            "question": "统计每个国家的客户数量",
            "should_clarify": False,
            "reason": "聚合方式和分组字段都明确"
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        result = check_if_needs_clarification(case["question"])
        needs_clarify = result["needs_clarification"]
        expected = case["should_clarify"]
        
        if needs_clarify == expected:
            print(f"✓ 测试 {i}: '{case['question']}'")
            print(f"  预期: {'需要澄清' if expected else '不需要澄清'}")
            print(f"  实际: {'需要澄清' if needs_clarify else '不需要澄清'}")
            if result.get("reasons"):
                print(f"  原因: {', '.join(result['reasons'])}")
            passed += 1
        else:
            print(f"✗ 测试 {i}: '{case['question']}'")
            print(f"  预期: {'需要澄清' if expected else '不需要澄清'}")
            print(f"  实际: {'需要澄清' if needs_clarify else '不需要澄清'}")
            failed += 1
    
    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_parse_clarification_response():
    """测试解析澄清问题响应"""
    print("\n" + "=" * 60)
    print("测试 2: 解析澄清问题响应")
    print("=" * 60)
    
    test_cases = [
        {
            "response": """问题: 请选择您想查询的发票时间范围

选项:
1. 最近一周
2. 最近一个月
3. 最近三个月
4. 今年""",
            "expected_question": "请选择您想查询的发票时间范围",
            "expected_options_count": 4
        },
        {
            "response": """澄清问题: 您希望如何统计客户信息？

选项:
1. 统计客户总数
2. 按城市分组统计
3. 按国家分组统计""",
            "expected_question": "您希望如何统计客户信息？",
            "expected_options_count": 3
        },
        {
            "response": """问题: 您想查询哪些专辑信息？

选项:
1. 专辑名称和艺术家
2. 专辑名称、艺术家和曲目数量
3. 所有专辑详细信息""",
            "expected_question": "您想查询哪些专辑信息？",
            "expected_options_count": 3
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        question, options = parse_clarification_response(case["response"])
        
        question_match = question == case["expected_question"]
        options_match = len(options) == case["expected_options_count"]
        
        if question_match and options_match:
            print(f"✓ 测试 {i}: 解析成功")
            print(f"  问题: {question}")
            print(f"  选项数量: {len(options)}")
            for j, opt in enumerate(options, 1):
                print(f"    {j}. {opt}")
            passed += 1
        else:
            print(f"✗ 测试 {i}: 解析失败")
            print(f"  预期问题: {case['expected_question']}")
            print(f"  实际问题: {question}")
            print(f"  预期选项数: {case['expected_options_count']}")
            print(f"  实际选项数: {len(options)}")
            failed += 1
    
    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_clarify_node_without_answer():
    """测试澄清节点（无用户回答）- 使用上下文记忆管理器"""
    print("\n" + "=" * 60)
    print("测试 3: 澄清节点 - 生成澄清问题 ")
    print("=" * 60)
    
    session_id = "test_session_001"
    # 清理之前的上下文管理器
    clear_context_manager(session_id)
    
    state: NL2SQLState = {
        "question": "查询最近的发票",
        "session_id": session_id,
        "user_id": "test_user",
        "dialog_history": [],
        "candidate_sql": "SELECT * FROM invoice ORDER BY InvoiceDate DESC LIMIT 100;",
        "clarification_answer": None,
        "clarification_count": 0,
        "max_clarifications": 3,
        "needs_clarification": None,
        "clarification_question": None,
        "clarification_options": None,
        "normalized_question": None,
        "timestamp": None,
        "intent": None,
        "sql_generated_at": None,
        "execution_result": None,
        "executed_at": None,
        "validation_result": None,
        "validation_errors": None,
        "validation_passed": None,
        "critique": None,
        "regeneration_count": 0,
        "max_regenerations": 3,
        "is_chat_response": False,
        "chat_response": None
    }
    
    try:
        # 初始化上下文管理器并添加查询
        context_manager = get_context_manager(session_id)
        context_manager.add_query(state["question"])
        
        # 验证查询已添加到历史
        history_before = context_manager.get_all_history()
        print(f"  添加查询后历史长度: {len(history_before)}")
        assert len(history_before) >= 1, "查询应该已添加到历史"
        assert history_before[-1]["type"] == "query", "最后一条应该是查询"
        
        result = clarify_node(state)
        
        #  检查上下文管理器是否正确更新
        history_after = context_manager.get_all_history()
        print(f"  澄清节点执行后历史长度: {len(history_after)}")
        
        if result.get("needs_clarification"):
            print("✓ 澄清节点执行成功")
            print(f"  需要澄清: {result.get('needs_clarification')}")
            print(f"  澄清问题: {result.get('clarification_question')}")
            if result.get("clarification_options"):
                print(f"  选项数量: {len(result['clarification_options'])}")
                for i, opt in enumerate(result["clarification_options"], 1):
                    print(f"    {i}. {opt}")
            print(f"  澄清次数: {result.get('clarification_count')}")
            print(f"  对话历史长度: {len(result.get('dialog_history', []))}")
            
            # 验证上下文管理器是否包含澄清问题
            if len(history_after) >= 2:
                last_entry = history_after[-1]
                if last_entry.get("type") == "clarification":
                    print("✓ 上下文管理器已正确记录澄清问题")
                    print(f"  澄清问题内容: {last_entry.get('content', '')[:50]}...")
                    if last_entry.get("options"):
                        print(f"  澄清选项数量: {len(last_entry['options'])}")
                else:
                    print(f"  上下文管理器未正确记录澄清问题，最后一条类型: {last_entry.get('type')}")
                    return False
            else:
                print("  历史记录数量不足，无法验证澄清问题")
                return False
            
            # 验证历史记录顺序：查询 -> 澄清问题
            assert history_after[0]["type"] == "query", "第一条应该是查询"
            assert history_after[-1]["type"] == "clarification", "最后一条应该是澄清问题"
            
            return True
        else:
            print("⚠️  未生成澄清问题（可能不需要澄清或生成失败）")
            return False
    except Exception as e:
        print(f"✗ 澄清节点执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理测试数据
        clear_context_manager(session_id)


def test_clarify_node_with_answer():
    """测试澄清节点（有用户回答）-  使用上下文记忆管理器"""
    print("\n" + "=" * 60)
    print("测试 4: 澄清节点 - 处理用户回答 ")
    print("=" * 60)
    
    session_id = "test_session_002"
    #  清理之前的上下文管理器
    clear_context_manager(session_id)
    
    state: NL2SQLState = {
        "question": "查询最近的发票",
        "session_id": session_id,
        "user_id": "test_user",
        "dialog_history": [],
        "candidate_sql": None,
        "clarification_answer": "最近一个月",  # 用户回答
        "clarification_question": "请选择您想查询的发票时间范围",
        "clarification_options": ["最近一周", "最近一个月", "最近三个月"],
        "clarification_count": 1,
        "max_clarifications": 3,
        "needs_clarification": True,
        "normalized_question": None,
        "timestamp": None,
        "intent": None,
        "sql_generated_at": None,
        "execution_result": None,
        "executed_at": None,
        "validation_result": None,
        "validation_errors": None,
        "validation_passed": None,
        "critique": None,
        "regeneration_count": 0,
        "max_regenerations": 3,
        "is_chat_response": False,
        "chat_response": None
    }
    
    try:
        # 初始化上下文管理器并添加历史记录
        context_manager = get_context_manager(session_id)
        context_manager.add_query(state["question"])
        context_manager.add_clarification(
            clarification_question=state["clarification_question"],
            options=state["clarification_options"]
        )
        
        # 验证历史记录已正确添加
        history_before = context_manager.get_all_history()
        print(f"  添加历史后长度: {len(history_before)}")
        assert len(history_before) >= 2, "应该有查询和澄清问题"
        assert history_before[0]["type"] == "query", "第一条应该是查询"
        assert history_before[-1]["type"] == "clarification", "最后一条应该是澄清问题"
        
        result = clarify_node(state)
        
        #  检查上下文管理器是否正确更新
        history_after = context_manager.get_all_history()
        print(f"  处理用户回答后历史长度: {len(history_after)}")
        
        if result.get("normalized_question"):
            print("✓ 用户回答处理成功")
            print(f"  原始问题: {state['question']}")
            print(f"  规范化问题: {result.get('normalized_question')}")
            print(f"  澄清回答已清空: {result.get('clarification_answer') is None}")
            print(f"  不再需要澄清: {not result.get('needs_clarification', True)}")
            print(f"  对话历史长度: {len(result.get('dialog_history', []))}")
            
            #  验证上下文管理器是否包含澄清回答
            if len(history_after) >= 3:
                last_entry = history_after[-1]
                if last_entry.get("type") == "clarification_answer":
                    print("✓ 上下文管理器已正确记录澄清回答")
                    print(f"  澄清回答内容: {last_entry.get('content', '')}")
                else:
                    print(f" 上下文管理器未正确记录澄清回答，最后一条类型: {last_entry.get('type')}")
                    return False
                
                # 验证历史记录顺序：查询 -> 澄清问题 -> 澄清回答
                assert history_after[0]["type"] == "query", "第一条应该是查询"
                assert history_after[1]["type"] == "clarification", "第二条应该是澄清问题"
                assert history_after[-1]["type"] == "clarification_answer", "最后一条应该是澄清回答"
            else:
                print("  历史记录数量不足，无法验证澄清回答")
                return False
            
            return True
        else:
            print("✗ 用户回答处理失败：未生成规范化问题")
            return False
    except Exception as e:
        print(f"✗ 用户回答处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理测试数据
        clear_context_manager(session_id)


def test_should_ask_clarification():
    """测试澄清判断函数"""
    print("\n" + "=" * 60)
    print("测试 5: 澄清判断函数")
    print("=" * 60)
    
    test_cases = [
        {
            "name": "需要澄清且未生成问题",
            "state": {
                "needs_clarification": True,
                "clarification_question": None,
                "clarification_answer": None
            },
            "expected": "clarify"
        },
        {
            "name": "用户已回答澄清问题",
            "state": {
                "needs_clarification": True,
                "clarification_question": "请选择时间范围",
                "clarification_answer": "最近一个月"
            },
            "expected": "regenerate"
        },
        {
            "name": "不需要澄清",
            "state": {
                "needs_clarification": False,
                "clarification_question": None,
                "clarification_answer": None
            },
            "expected": "continue"
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        # 创建完整state
        state: NL2SQLState = {
            "question": "测试问题",
            "session_id": "test",
            **case["state"],
            "user_id": None,
            "dialog_history": [],
            "candidate_sql": None,
            "clarification_count": 0,
            "max_clarifications": 3,
            "clarification_options": None,
            "normalized_question": None,
            "timestamp": None,
            "intent": None,
            "sql_generated_at": None,
            "execution_result": None,
            "executed_at": None,
            "validation_result": None,
            "validation_errors": None,
            "validation_passed": None,
            "critique": None,
            "regeneration_count": 0,
            "max_regenerations": 3
        }
        
        result = should_ask_clarification(state)
        expected = case["expected"]
        
        if result == expected:
            print(f"✓ 测试 {i}: {case['name']}")
            print(f"  预期: {expected}, 实际: {result}")
            passed += 1
        else:
            print(f"✗ 测试 {i}: {case['name']}")
            print(f"  预期: {expected}, 实际: {result}")
            failed += 1
    
    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_full_clarification_flow():
    """测试完整的澄清流程（需要LLM和数据库）-: 使用上下文记忆管理器"""
    print("\n" + "=" * 60)
    print("测试 6: 完整澄清流程（端到端测试）")
    print("=" * 60)
    print("注意：此测试需要LLM API和数据库连接")
    
    session_id = "test_full_flow"
    #  清理之前的上下文管理器
    clear_context_manager(session_id)
    
    try:
        # 第一轮：用户提问（应该触发澄清）
        print("\n--- 第一轮：用户提问 ---")
        result1 = run_query(
            question="查询最近的发票",
            session_id=session_id,
            user_id="test_user"
        )
        
        #  检查上下文管理器
        context_manager = get_context_manager(session_id)
        history1 = context_manager.get_all_history()
        print(f"  第一轮后上下文历史长度: {len(history1)}")
        
        needs_clarify = result1.get("needs_clarification")
        clarification_question = result1.get("clarification_question")
        
        if needs_clarify and clarification_question:
            print("✓ 第一轮：成功生成澄清问题")
            print(f"  澄清问题: {clarification_question}")
            if result1.get("clarification_options"):
                print("  选项:")
                for i, opt in enumerate(result1.get("clarification_options", []), 1):
                    print(f"    {i}. {opt}")
            
            #  验证上下文管理器包含澄清问题
            if len(history1) >= 2:
                last_entry = history1[-1]
                if last_entry.get("type") == "clarification":
                    print("✓ 上下文管理器已记录澄清问题")
                else:
                    print(f"⚠️  上下文管理器未记录澄清问题，类型: {last_entry.get('type')}")
            
            # 模拟用户选择第一个选项
            user_answer = result1.get("clarification_options", [])[0] if result1.get("clarification_options") else "最近一个月"
            
            print(f"\n--- 第二轮：用户回答 '{user_answer}' ---")
            result2 = run_query(
                question="查询最近的发票",
                session_id=session_id,  # 相同session
                user_id="test_user",
                clarification_answer=user_answer
            )
            
            # 检查上下文管理器更新
            history2 = context_manager.get_all_history()
            print(f"  第二轮后上下文历史长度: {len(history2)}")
            
            normalized_question = result2.get("normalized_question")
            candidate_sql = result2.get("candidate_sql")
            
            if normalized_question:
                print("✓ 第二轮：成功处理用户回答")
                print(f"  规范化问题: {normalized_question}")
                
                #  验证上下文管理器包含澄清回答
                if len(history2) >= 3:
                    last_entry = history2[-1]
                    if last_entry.get("type") == "clarification_answer":
                        print("✓ 上下文管理器已记录澄清回答")
                    else:
                        print(f"  上下文管理器未记录澄清回答，类型: {last_entry.get('type')}")
                
                if candidate_sql:
                    print(f"  生成的SQL: {candidate_sql[:100]}...")
                    
                    #  验证完整流程的历史记录顺序
                    print("\n  验证历史记录顺序:")
                    for i, entry in enumerate(history2):
                        entry_type = entry.get("type", "unknown")
                        content_preview = entry.get("content", "")[:30]
                        print(f"    {i+1}. {entry_type}: {content_preview}...")
                    
                    return True
                else:
                    print("  SQL未生成（可能流程中断）")
                    return False
            else:
                print("✗ 第二轮：处理用户回答失败")
                return False
        else:
            print("  第一轮：未生成澄清问题（可能问题已经足够明确）")
            return False
            
    except Exception as e:
        print(f"✗ 完整流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理测试数据
        clear_context_manager(session_id)


def test_max_clarifications():
    """测试最大澄清次数限制 -  使用上下文记忆管理器"""
    print("\n" + "=" * 60)
    print("测试 7: 最大澄清次数限制 ")
    print("=" * 60)
    
    session_id = "test_max_clarify"
    clear_context_manager(session_id)
    
    state: NL2SQLState = {
        "question": "查询专辑",  # 非常模糊的问题
        "session_id": session_id,
        "user_id": "test_user",
        "dialog_history": [],
        "candidate_sql": None,
        "clarification_answer": None,
        "clarification_count": 3,  # 已达到最大次数
        "max_clarifications": 3,
        "needs_clarification": None,
        "clarification_question": None,
        "clarification_options": None,
        "normalized_question": None,
        "timestamp": None,
        "intent": None,
        "sql_generated_at": None,
        "execution_result": None,
        "executed_at": None,
        "validation_result": None,
        "validation_errors": None,
        "validation_passed": None,
        "critique": None,
        "regeneration_count": 0,
        "max_regenerations": 3,
        "is_chat_response": False,
        "chat_response": None
    }
    
    try:
        # 初始化上下文管理器
        context_manager = get_context_manager(session_id)
        context_manager.add_query(state["question"])
        
        result = clarify_node(state)
        
        if not result.get("needs_clarification"):
            print("✓ 达到最大澄清次数后，不再生成澄清问题")
            print(f"  澄清次数: {result.get('clarification_count')}")
            print(f"  需要澄清: {result.get('needs_clarification')}")
            
            # 验证上下文管理器未添加新的澄清问题
            history = context_manager.get_all_history()
            print(f"  上下文历史长度: {len(history)}")
            # 应该只有查询，没有澄清问题
            clarification_entries = [h for h in history if h.get("type") == "clarification"]
            if len(clarification_entries) == 0:
                print("✓ 上下文管理器未添加澄清问题（符合预期）")
            else:
                print(f"⚠️  上下文管理器添加了 {len(clarification_entries)} 个澄清问题（不符合预期）")
                return False
            
            return True
        else:
            print("✗ 达到最大澄清次数后，仍然生成澄清问题")
            return False
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        clear_context_manager(session_id)


def test_context_memory_integration():
    """测试上下文记忆管理器与澄清功能的集成 """
    print("\n" + "=" * 60)
    print("测试 8: 上下文记忆管理器集成")
    print("=" * 60)
    
    session_id = "test_context_integration"
    clear_context_manager(session_id)
    
    try:
        context_manager = get_context_manager(session_id)
        
        # 测试1: 添加查询
        context_manager.add_query("查询客户信息")
        history = context_manager.get_all_history()
        assert len(history) == 1, "应该有1条历史记录"
        assert history[0]["type"] == "query", "应该是查询类型"
        print("✓ 测试1: 添加查询成功")
        
        # 测试2: 添加澄清问题
        context_manager.add_clarification(
            clarification_question="您想查询哪些客户信息？",
            options=["客户姓名和城市", "客户姓名和国家", "所有客户详细信息"],
            reasons=["字段需求不明确"]
        )
        history = context_manager.get_all_history()
        assert len(history) == 2, "应该有2条历史记录"
        assert history[-1]["type"] == "clarification", "应该是澄清类型"
        assert len(history[-1].get("options", [])) == 3, "应该有3个选项"
        print("✓ 测试2: 添加澄清问题成功")
        
        # 测试3: 添加澄清回答
        context_manager.add_clarification_answer("客户姓名和城市")
        history = context_manager.get_all_history()
        assert len(history) == 3, "应该有3条历史记录"
        assert history[-1]["type"] == "clarification_answer", "应该是澄清回答类型"
        print("✓ 测试3: 添加澄清回答成功")
        
        # 测试4: 格式化上下文用于澄清
        context_text = context_manager.format_context_for_clarification(
            question="查询客户信息",
            candidate_sql=None
        )
        assert "对话历史上下文" in context_text, "应该包含对话历史上下文"
        assert "用户: 查询客户信息" in context_text, "应该包含用户查询"
        print("✓ 测试4: 格式化澄清上下文成功")
        
        # 测试5: 检查是否需要澄清（使用上下文管理器）
        clarification_check = context_manager.check_needs_clarification(
            question="查询专辑",
            candidate_sql=None
        )
        assert "needs_clarification" in clarification_check, "应该返回澄清检查结果"
        print("✓ 测试5: 上下文管理器澄清检查成功")
        
        # 测试6: 获取最近历史
        recent = context_manager.get_recent_history(2)
        assert len(recent) == 2, "应该返回最近2条记录"
        print("✓ 测试6: 获取最近历史成功")
        
        # 测试7: 清空历史
        context_manager.clear_history()
        history = context_manager.get_all_history()
        assert len(history) == 0, "历史应该被清空"
        print("✓ 测试7: 清空历史成功")
        
        return True
    except Exception as e:
        print(f"✗ 上下文记忆管理器集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        clear_context_manager(session_id)


def test_multi_turn_clarification():
    """测试多轮对话中的澄清功能 """
    print("\n" + "=" * 60)
    print("测试 9: 多轮对话澄清")
    print("=" * 60)
    print("注意：此测试需要LLM API支持")
    
    session_id = "test_multi_turn"
    clear_context_manager(session_id)
    
    try:
        from tools.llm_client import llm_client
        # 测试LLM连接
        test_prompt = "测试"
        llm_client.chat(prompt=test_prompt)
    except Exception as e:
        print(f"⚠️  LLM未配置或连接失败: {e}")
        print("  跳过多轮对话澄清测试")
        return False
    
    try:
        context_manager = get_context_manager(session_id)
        
        # 第一轮：模糊查询
        print("\n--- 第一轮：模糊查询 ---")
        state1: NL2SQLState = {
            "question": "查询专辑信息",
            "session_id": session_id,
            "user_id": "test_user",
            "dialog_history": [],
            "candidate_sql": None,
            "clarification_answer": None,
            "clarification_count": 0,
            "max_clarifications": 3,
            "needs_clarification": None,
            "clarification_question": None,
            "clarification_options": None,
            "normalized_question": None,
            "timestamp": None,
            "intent": None,
            "sql_generated_at": None,
            "execution_result": None,
            "executed_at": None,
            "validation_result": None,
            "validation_errors": None,
            "validation_passed": None,
            "critique": None,
            "regeneration_count": 0,
            "max_regenerations": 3,
            "is_chat_response": False,
            "chat_response": None
        }
        
        context_manager.add_query(state1["question"])
        result1 = clarify_node(state1)
        
        if result1.get("needs_clarification"):
            print("✓ 第一轮：生成澄清问题")
            clarification_question1 = result1.get("clarification_question")
            print(f"  澄清问题: {clarification_question1}")
            
            # 用户回答
            user_answer1 = result1.get("clarification_options", [])[0] if result1.get("clarification_options") else "最近一个月"
            
            # 第二轮：基于澄清回答继续
            print(f"\n--- 第二轮：用户回答 '{user_answer1}' ---")
            state2: NL2SQLState = {
                **state1,
                "clarification_answer": user_answer1,
                "clarification_question": clarification_question1,
                "clarification_count": 1
            }
            
            result2 = clarify_node(state2)
            
            if result2.get("normalized_question"):
                print("✓ 第二轮：处理澄清回答成功")
                print(f"  规范化问题: {result2.get('normalized_question')}")
                
                # 验证上下文历史
                history = context_manager.get_all_history()
                print(f"\n  上下文历史记录数: {len(history)}")
                print("  历史记录类型序列:")
                for i, entry in enumerate(history):
                    print(f"    {i+1}. {entry.get('type')}: {entry.get('content', '')[:40]}...")
                
                # 验证历史记录顺序
                expected_types = ["query", "clarification", "clarification_answer"]
                actual_types = [h.get("type") for h in history[:3]]
                if actual_types == expected_types:
                    print("✓ 历史记录顺序正确")
                    return True
                else:
                    print(f"✗ 历史记录顺序不正确，预期: {expected_types}, 实际: {actual_types}")
                    return False
            else:
                print("✗ 第二轮：处理澄清回答失败")
                return False
        else:
            print("⚠️  第一轮：未生成澄清问题（可能问题已经足够明确）")
            return False
            
    except Exception as e:
        print(f"✗ 多轮对话澄清测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        clear_context_manager(session_id)


def main():
    """运行所有测试"""
    print("=" * 60)
    print(" Dialog Clarification 功能测试")
    print("=" * 60)
    
    results = []
    
    # 基础功能测试（不需要LLM和数据库）
    results.append(("澄清判据检查", test_clarification_criteria()))
    results.append(("解析澄清响应", test_parse_clarification_response()))
    results.append(("澄清判断函数", test_should_ask_clarification()))
    results.append(("上下文记忆管理器集成", test_context_memory_integration()))
    results.append(("最大澄清次数", test_max_clarifications()))
    
    # 需要LLM的测试
    print("\n" + "=" * 60)
    print("以下测试需要LLM API支持")
    print("=" * 60)
    
    try:
        from tools.llm_client import llm_client
        # 测试LLM连接
        test_prompt = "测试"
        llm_client.chat(prompt=test_prompt)
        
        results.append(("生成澄清问题", test_clarify_node_without_answer()))
        results.append(("处理用户回答", test_clarify_node_with_answer()))
        results.append(("多轮对话澄清", test_multi_turn_clarification()))
        
        # 完整流程测试（需要数据库）
        print("\n" + "=" * 60)
        print("以下测试需要数据库连接")
        print("=" * 60)
        
        try:
            from tools.db import db_client
            if db_client.test_connection():
                results.append(("完整澄清流程", test_full_clarification_flow()))
            else:
                print("⚠️  数据库未连接，跳过完整流程测试")
        except Exception as e:
            print(f"⚠️  数据库连接失败: {e}")
            print("  跳过完整流程测试")
    except Exception as e:
        print(f"⚠️  LLM未配置或连接失败: {e}")
        print("  跳过需要LLM的测试")
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())

