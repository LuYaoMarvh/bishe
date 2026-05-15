"""
交互式NL2SQL测试工具
支持多轮对话、澄清问答和完整流程测试
"""
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import json
from datetime import datetime

# 添加项目根目录到路径
# 安全修复：test文件在test子目录中，需要使用parent.parent获取项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from graphs.base_graph import run_query
from graphs.state import NL2SQLState


class InteractiveTester:
    """交互式NL2SQL测试器"""
    
    def __init__(self):
        self.session_id = f"interactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.user_id = "interactive_user"
        self.dialog_history = []
        self.current_state: Optional[NL2SQLState] = None
        
        # 初始化上下文记忆管理器
        from graphs.utils.context_memory import get_context_manager
        self.context_manager = get_context_manager(self.session_id, max_history=10)
        
    def print_header(self):
        """打印欢迎信息"""
        print("\n" + "=" * 70)
        print(" NL2SQL 交互式测试工具")
        print("=" * 70)
        print(f"会话ID: {self.session_id}")
        print(f"用户ID: {self.user_id}")
        print("\n输入 'help' 查看命令，输入 'quit' 退出")
        print("=" * 70 + "\n")
    
    def print_help(self):
        """打印帮助信息"""
        print("\n" + "=" * 70)
        print("📖 命令帮助")
        print("=" * 70)
        print("直接输入问题: 进行SQL查询")
        print(" 示例: 查询每个客户的订单数量")
        print()
        print("命令:")
        print("  help          - 显示此帮助信息")
        print("  quit / exit   - 退出程序")
        print("  clear         - 清屏")
        print("  history       - 显示对话历史")
        print("  state         - 显示当前状态信息")
        print("  sql           - 显示最后生成的SQL")
        print("  answer        - 显示最后生成的答案")
        print("  session       - 显示会话信息")
        print("=" * 70 + "\n")
    
    def print_separator(self, title: str = ""):
        """打印分隔线"""
        if title:
            print(f"\n{'=' * 70}")
            print(f"  {title}")
            print(f"{'=' * 70}")
        else:
            print("\n" + "-" * 70)
    
    def display_state(self):
        """显示当前状态"""
        if not self.current_state:
            print(" 还没有执行过查询")
            return
        
        print("\n" + "=" * 70)
        print(" 当前状态")
        print("=" * 70)
        
        # 基本信息
        print(f"\n问题: {self.current_state.get('question', 'N/A')}")
        print(f"会话ID: {self.current_state.get('session_id', 'N/A')}")
        print(f"时间戳: {self.current_state.get('timestamp', 'N/A')}")
        
        # 意图信息
        intent = self.current_state.get('intent')
        if intent:
            print(f"\n意图解析:")
            print(f"  类型: {intent.get('type', 'N/A')}")
            print(f"  限制: {intent.get('limit', 'N/A')}")
            print(f"  时间范围: {intent.get('has_time_range', False)}")
        
        # SQL信息
        sql = self.current_state.get('candidate_sql')
        if sql:
            print(f"\n生成的SQL:")
            print(f"  {sql}")
        
        # 验证信息
        validation_passed = self.current_state.get('validation_passed')
        if validation_passed is not None:
            status = "✓ 通过" if validation_passed else "✗ 失败"
            print(f"\nSQL验证: {status}")
            if not validation_passed:
                errors = self.current_state.get('validation_errors', [])
                if errors:
                    print(f"  错误: {', '.join(errors)}")
        
        # 执行结果
        execution_result = self.current_state.get('execution_result')
        if execution_result:
            if execution_result.get('ok'):
                print(f"\n执行结果: ✓ 成功")
                print(f"  行数: {execution_result.get('row_count', 0)}")
                print(f"  列: {', '.join(execution_result.get('columns', []))}")
            else:
                print(f"\n执行结果: ✗ 失败")
                print(f"  错误: {execution_result.get('error', 'N/A')}")
        
        # 答案
        answer = self.current_state.get('answer')
        if answer:
            print(f"\n生成的答案: ✓")
            print(f"  长度: {len(answer)} 字符")
        
        # 澄清信息
        needs_clarification = self.current_state.get('needs_clarification')
        if needs_clarification:
            print(f"\n澄清状态:   需要澄清")
            print(f"  问题: {self.current_state.get('clarification_question', 'N/A')}")
            print(f"  轮次: {self.current_state.get('clarification_count', 0)}/3")
        
        print("=" * 70 + "\n")
    
    def display_sql(self):
        """显示最后生成的SQL"""
        if not self.current_state:
            print(" 还没有执行过查询")
            return
        
        sql = self.current_state.get('candidate_sql')
        if sql:
            print("\n" + "=" * 70)
            print("生成的SQL")
            print("=" * 70)
            print(sql)
            print("=" * 70 + "\n")
        else:
            print(" 还没有生成SQL")
    
    def display_answer(self):
        """显示最后生成的答案"""
        if not self.current_state:
            print(" 还没有执行过查询")
            return
        
        answer = self.current_state.get('answer')
        if answer:
            print("\n" + "=" * 70)
            print(" 自然语言答案")
            print("=" * 70)
            print(answer)
            print("=" * 70 + "\n")
        else:
            print(" 还没有生成答案")
    
    def display_history(self):
        history = self.context_manager.get_all_history()
        
        if not history:
            print("  对话历史为空")
            return
        
        print("\n" + "=" * 70)
        print("对话历史 ")
        print("=" * 70)
        
        for i, entry in enumerate(history, 1):
            role = entry.get('role', 'unknown')
            content = entry.get('content', '')
            timestamp = entry.get('timestamp', '')
            entry_type = entry.get('type', '')
            
            # 格式化时间戳
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = timestamp[:8] if len(timestamp) > 8 else timestamp
            else:
                time_str = ""
            
            # 根据类型显示不同的图标
            if role == 'user':
                if entry_type == 'query':
                    print(f"\n[{i}]  用户查询 ({time_str})")
                elif entry_type == 'clarification_answer':
                    print(f"\n[{i}]  澄清回答 ({time_str})")
                else:
                    print(f"\n[{i}]  用户 ({time_str})")
            elif role == 'assistant':
                if entry_type == 'answer':
                    print(f"\n[{i}]  系统答案 ({time_str})")
                    # 显示SQL（如果有）
                    sql = entry.get('sql')
                    if sql:
                        print(f"   SQL: {sql[:100]}..." if len(sql) > 100 else f"   SQL: {sql}")
                elif entry_type == 'clarification':
                    print(f"\n[{i}]  澄清问题 ({time_str})")
                    options = entry.get('options', [])
                    if options:
                        print(f"   选项: {', '.join(options)}")
                elif entry_type == 'chat':
                    print(f"\n[{i}]  聊天回复 ({time_str})")
                else:
                    print(f"\n[{i}]  助手 ({time_str})")
            
            # 显示内容（截断长内容）
            if len(content) > 200:
                print(f"   {content[:200]}...")
            else:
                print(f"   {content}")
        
        print(f"\n总计: {len(history)} 条记录")
        print("=" * 70 + "\n")
    
    def display_session_info(self):
        """显示会话信息 包含上下文记忆信息"""
        print("\n" + "=" * 70)
        print(" 会话信息")
        print("=" * 70)
        print(f"会话ID: {self.session_id}")
        print(f"用户ID: {self.user_id}")
        print(f"对话轮次: {len(self.context_manager.get_all_history())}")
        print(f"最大历史长度: {self.context_manager.max_history}")
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("\n上下文记忆状态:")
        history = self.context_manager.get_all_history()
        if history:
            query_count = sum(1 for h in history if h.get('type') == 'query')
            answer_count = sum(1 for h in history if h.get('type') == 'answer')
            clarification_count = sum(1 for h in history if h.get('type') == 'clarification')
            chat_count = sum(1 for h in history if h.get('type') == 'chat')
            print(f"  - 查询: {query_count} 次")
            print(f"  - 答案: {answer_count} 次")
            print(f"  - 澄清: {clarification_count} 次")
            print(f"  - 聊天: {chat_count} 次")
        else:
            print("  - 暂无历史记录")
        print("=" * 70 + "\n")
    
    def handle_clarification(self, state: NL2SQLState) -> Optional[str]:
        """处理澄清问题"""
        if not state.get('needs_clarification'):
            return None
        
        clarification_question = state.get('clarification_question')
        clarification_options = state.get('clarification_options', [])
        clarification_count = state.get('clarification_count', 0)
        
        self.print_separator("需要澄清问题")
        print(f"问题: {clarification_question}")
        print(f"澄清轮次: {clarification_count}/3")
        
        if clarification_options:
            print("\n请选择:")
            for i, opt in enumerate(clarification_options, 1):
                print(f"  {i}. {opt}")
        
        print("\n输入选项编号或直接输入答案，输入 'skip' 跳过澄清")
        
        # 记录澄清问题到历史
        self.dialog_history.append({
            'role': 'clarification',
            'content': clarification_question,
            'options': clarification_options,
            'timestamp': datetime.now().isoformat()
        })
        
        # 获取用户输入
        user_input = input("\n> ").strip()
        
        if user_input.lower() == 'skip':
            return None
        
        # 如果是数字，选择对应选项
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(clarification_options):
                return clarification_options[idx]
        
        # 否则直接返回用户输入
        return user_input if user_input else None
    
    def run_query_interactive(self, question: str, clarification_answer: Optional[str] = None):
        """运行查询并处理交互"""
        print(f"\n{'=' * 70}")
        print(f" 处理查询: {question}")
        print(f"{'=' * 70}\n")

        conversation_history = self.context_manager.get_all_history()
        
        # 记录用户问题（用于本地显示）
        self.dialog_history.append({
            'role': 'user',
            'content': question,
            'timestamp': datetime.now().isoformat()
        })
        
        try:
            #  运行查询，传入历史上下文
            result = run_query(
                question=question,
                session_id=self.session_id,
                user_id=self.user_id,
                clarification_answer=clarification_answer,
                conversation_history=conversation_history  #  传递历史上下文
            )
            
            self.current_state = result
            
            # 更新上下文管理器（从result中获取最新的历史）
            updated_history = result.get('dialog_history', [])
            if updated_history:
                # 同步历史到上下文管理器
                self.context_manager.conversation_history = updated_history
                self.context_manager._trim_history()
            
            # 检查是否需要澄清
            if result.get('needs_clarification'):
                clarification_answer = self.handle_clarification(result)
                
                if clarification_answer:
                    # 记录用户回答（用于本地显示）
                    self.dialog_history.append({
                        'role': 'user',
                        'content': f"澄清回答: {clarification_answer}",
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # 重新运行查询，带上澄清答案（历史会自动传递）
                    return self.run_query_interactive(question, clarification_answer)
                else:
                    print("  跳过澄清，继续处理...")
            
            # 显示SQL
            sql = result.get('candidate_sql')
            if sql:
                self.print_separator("生成的SQL")
                print(sql)
            
            # 显示执行结果
            execution_result = result.get('execution_result')
            if execution_result:
                if execution_result.get('ok'):
                    self.print_separator("执行结果")
                    print(f"✓ 成功")
                    print(f"  行数: {execution_result.get('row_count', 0)}")
                    print(f"  列: {', '.join(execution_result.get('columns', []))}")
                    
                    # 显示前几行数据
                    rows = execution_result.get('rows', [])
                    if rows and len(rows) <= 5:
                        print(f"\n数据:")
                        for i, row in enumerate(rows, 1):
                            print(f"  [{i}] {row}")
                    elif rows:
                        print(f"\n前3条数据:")
                        for i, row in enumerate(rows[:3], 1):
                            print(f"  [{i}] {row}")
                        print(f"  ... 还有 {len(rows) - 3} 条记录")
                else:
                    self.print_separator("执行结果")
                    print(f"✗ 失败: {execution_result.get('error', 'N/A')}")
            
            # 显示答案
            answer = result.get('answer')
            if answer:
                self.print_separator("自然语言答案")
                print(answer)
                
                # 记录助手回答
                self.dialog_history.append({
                    'role': 'assistant',
                    'content': answer,
                    'timestamp': datetime.now().isoformat()
                })
            
            return result
            
        except Exception as e:
            print(f"\n✗ 错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def run(self):
        """运行交互式测试"""
        self.print_header()
        
        while True:
            try:
                # 获取用户输入
                user_input = input("\n💬 请输入问题 (输入 'help' 查看帮助): ").strip()
                
                if not user_input:
                    continue
                
                # 处理命令
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\n👋 再见！")
                    break
                
                elif user_input.lower() == 'help':
                    self.print_help()
                
                elif user_input.lower() == 'clear':
                    import os
                    os.system('cls' if os.name == 'nt' else 'clear')
                    self.print_header()
                
                elif user_input.lower() == 'history':
                    self.display_history()
                
                elif user_input.lower() == 'state':
                    self.display_state()
                
                elif user_input.lower() == 'sql':
                    self.display_sql()
                
                elif user_input.lower() == 'answer':
                    self.display_answer()
                
                elif user_input.lower() == 'session':
                    self.display_session_info()
                
                else:
                    # 作为问题处理
                    self.run_query_interactive(user_input)
                
            except KeyboardInterrupt:
                print("\n\n⚠️  中断操作")
                continue
            except EOFError:
                print("\n\n👋 再见！")
                break
            except Exception as e:
                print(f"\n✗ 发生错误: {e}")
                import traceback
                traceback.print_exc()


def main():
    """主函数"""
    try:
        tester = InteractiveTester()
        tester.run()
    except Exception as e:
        print(f"\n✗ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

