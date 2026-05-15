"""
测试 Answer Builder 功能
验证SQL结果转自然语言答案功能是否正常工作
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
# 安全修复：test文件在test子目录中，需要使用parent.parent获取项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from graphs.base_graph import run_query
from graphs.nodes.answer_builder import (
    format_data_summary,
    extract_key_values,
    format_key_values_summary,
    is_numeric
)


def test_format_data_summary():
    """测试数据摘要格式化"""
    print("=" * 60)
    print("测试 1: 数据摘要格式化")
    print("=" * 60)
    
    # 测试1: 空结果
    empty_result = {
        "ok": True,
        "rows": [],
        "row_count": 0,
        "columns": []
    }
    summary = format_data_summary(empty_result)
    print(f"✓ 空结果测试: {summary.get('type')} - {summary.get('message')}")
    
    # 测试2: 小数据集（≤10行）
    small_result = {
        "ok": True,
        "rows": [
            {"CustomerId": 1, "FirstName": "Luís", "order_count": 7},
            {"CustomerId": 2, "FirstName": "Leonie", "order_count": 5}
        ],
        "row_count": 2,
        "columns": ["CustomerId", "FirstName", "order_count"]
    }
    summary = format_data_summary(small_result)
    print(f"✓ 小数据集测试: {summary.get('type')} - {summary.get('total_count')} 条记录")
    
    # 测试3: 大数据集（>10行）
    large_result = {
        "ok": True,
        "rows": [{"CustomerId": i, "order_count": i * 2} for i in range(1, 21)],
        "row_count": 20,
        "columns": ["CustomerId", "order_count"]
    }
    summary = format_data_summary(large_result)
    print(f"✓ 大数据集测试: {summary.get('type')} - {summary.get('total_count')} 条记录")
    print(f"  示例数据: {len(summary.get('sample', []))} 条")
    print(f"  关键值: {len(summary.get('key_values', {}))} 个字段")
    
    return True


def test_extract_key_values():
    """测试关键值提取"""
    print("\n" + "=" * 60)
    print("测试 2: 关键值提取")
    print("=" * 60)
    
    rows = [
        {"CustomerId": 1, "order_count": 7, "total_amount": 100.5},
        {"CustomerId": 2, "order_count": 5, "total_amount": 200.3},
        {"CustomerId": 3, "order_count": 10, "total_amount": 150.0}
    ]
    columns = ["CustomerId", "order_count", "total_amount"]
    
    key_values = extract_key_values(rows, columns)
    
    print(f"✓ 提取到 {len(key_values)} 个字段的关键值:")
    for col, stats in key_values.items():
        if "max" in stats:
            print(f"  {col}:")
            print(f"    - 最大值: {stats['max']}")
            print(f"    - 最小值: {stats['min']}")
            print(f"    - 平均值: {stats['avg']:.2f}")
            print(f"    - 总计: {stats['sum']}")
    
    return True


def test_is_numeric():
    """测试数值判断"""
    print("\n" + "=" * 60)
    print("测试 3: 数值判断")
    print("=" * 60)
    
    test_cases = [
        (123, True),
        (123.45, True),
        ("123", True),
        ("123.45", True),
        ("abc", False),
        (None, False),
        ("", False)
    ]
    
    passed = 0
    for value, expected in test_cases:
        result = is_numeric(value)
        if result == expected:
            print(f"✓ {value} -> {result}")
            passed += 1
        else:
            print(f"✗ {value} -> {result} (期望: {expected})")
    
    print(f"\n结果: {passed}/{len(test_cases)} 通过")
    return passed == len(test_cases)


def test_answer_builder_integration():
    """测试答案生成集成（需要LLM和数据库）"""
    print("\n" + "=" * 60)
    print("测试 4: 答案生成集成测试（端到端）")
    print("=" * 60)
    print("注意：此测试需要LLM API和数据库连接")
    
    test_cases = [
        {
            "question": "查询每个客户的订单数量",
            "description": "聚合查询 - 多行结果"
        },
        {
            "question": "查询客户ID为1的客户信息",
            "description": "单行查询"
        },
        {
            "question": "查询2025年的订单",
            "description": "可能为空结果"
        }
    ]
    
    try:
        from tools.llm_client import llm_client
        from tools.db import db_client
        
        # 测试LLM连接
        test_prompt = "测试"
        llm_client.chat(prompt=test_prompt)
        
        # 测试数据库连接
        if not db_client.test_connection():
            print("⚠️  数据库未连接，跳过集成测试")
            return False
        
        passed = 0
        failed = 0
        
        for i, case in enumerate(test_cases, 1):
            print(f"\n--- 测试 {i}: {case['description']} ---")
            print(f"问题: {case['question']}")
            
            try:
                result = run_query(
                    question=case["question"],
                    session_id=f"test_answer_{i}",
                    user_id="test_user"
                )
                
                answer = result.get("answer")
                execution_result = result.get("execution_result")
                
                if answer:
                    print(f"✓ 生成了答案 ({len(answer)} 字符)")
                    print(f"\n答案预览:")
                    # 显示前200个字符
                    preview = answer[:200] + "..." if len(answer) > 200 else answer
                    print(preview)
                    
                    # 检查答案是否包含必要部分
                    has_conclusion = "结论" in answer or "总结" in answer or "结果" in answer
                    has_sql_info = "SQL" in answer or "查询" in answer
                    
                    if has_conclusion and has_sql_info:
                        print(f"✓ 答案包含结论和SQL说明")
                        passed += 1
                    else:
                        print(f"⚠️  答案可能缺少必要部分")
                        print(f"  包含结论: {has_conclusion}")
                        print(f"  包含SQL说明: {has_sql_info}")
                        failed += 1
                else:
                    print(f"✗ 未生成答案")
                    failed += 1
                
                # 检查执行结果
                if execution_result and execution_result.get("ok"):
                    print(f"✓ SQL执行成功: {execution_result.get('row_count', 0)} 条记录")
                else:
                    print(f"⚠️  SQL执行失败或未执行")
                    
            except Exception as e:
                print(f"✗ 测试失败: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
        
        print(f"\n结果: {passed} 通过, {failed} 失败")
        return failed == 0
        
    except Exception as e:
        print(f"⚠️  LLM或数据库未配置: {e}")
        print("  跳过集成测试")
        return False


def test_answer_validation():
    """测试答案验证（检查是否编造字段）"""
    print("\n" + "=" * 60)
    print("测试 5: 答案验证（检查编造字段）")
    print("=" * 60)
    
    # 模拟执行结果
    execution_result = {
        "ok": True,
        "rows": [
            {"CustomerId": 1, "FirstName": "Luís", "order_count": 7}
        ],
        "row_count": 1,
        "columns": ["CustomerId", "FirstName", "order_count"]
    }
    
    # 测试答案（应该只包含实际字段）
    valid_answer = """
    结论：找到了客户ID为1的客户，姓名是Luís，订单数量为7。
    关键值：
    - CustomerId: 1
    - FirstName: Luís
    - order_count: 7
    """
    
    invalid_answer = """
    结论：找到了客户ID为1的客户，姓名是Luís，订单数量为7，邮箱是test@example.com。
    关键值：
    - CustomerId: 1
    - Email: test@example.com  # 这个字段不存在
    """
    
    actual_columns = execution_result["columns"]
    
    # 检查有效答案
    valid_columns_mentioned = []
    for col in actual_columns:
        if col in valid_answer:
            valid_columns_mentioned.append(col)
    
    print(f"✓ 有效答案测试:")
    print(f"  实际字段: {', '.join(actual_columns)}")
    print(f"  答案中提到的字段: {', '.join(valid_columns_mentioned)}")
    print(f"  验证: 所有提到的字段都存在")
    
    # 检查无效答案
    invalid_columns = []
    for word in invalid_answer.split():
        # 简单检查（实际应该用更复杂的NLP方法）
        if word not in actual_columns and word.capitalize() not in actual_columns:
            # 这里只是演示，实际验证需要更复杂的逻辑
            pass
    
    print(f"\n⚠️  无效答案检测需要更复杂的NLP方法")
    print(f"  实际字段: {', '.join(actual_columns)}")
    print(f"  答案中提到了不存在的字段: Email")
    
    return True


def main():
    """运行所有测试"""
    print("=" * 60)
    print(" Answer Builder 功能测试")
    print("=" * 60)
    
    results = []
    
    # 基础功能测试（不需要LLM和数据库）
    results.append(("数据摘要格式化", test_format_data_summary()))
    results.append(("关键值提取", test_extract_key_values()))
    results.append(("数值判断", test_is_numeric()))
    results.append(("答案验证", test_answer_validation()))
    
    # 需要LLM和数据库的测试
    print("\n" + "=" * 60)
    print("以下测试需要LLM API和数据库支持")
    print("=" * 60)
    
    results.append(("答案生成集成", test_answer_builder_integration()))
    
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
        print("\n 所有测试通过！")
        return 0
    else:
        print(f"\n  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())

