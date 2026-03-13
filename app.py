"""
NL2SQL Web 应用 - Flask 后端（更新版）
集成统计追踪和真实数据更新
"""
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import sys
from pathlib import Path
from datetime import datetime
import uuid
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from graphs.base_graph import run_query
from tools.db import db_client
from stats_tracker import stats_tracker  # 导入统计追踪器

app = Flask(__name__)
app.secret_key = 'lqr123456'  # 已更新
CORS(app)

# 全局变量：存储会话状态
sessions_store = {}


@app.route('/')
def index():
    """主页面"""
    if 'session_id' not in session:
        session['session_id'] = f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        session['user_id'] = 'web_user'

    # 获取数据库信息
    try:
        tables = db_client.get_table_names()
        db_status = {
            'connected': True,
            'database': db_client.database,
            'tables_count': len(tables)
        }
    except Exception as e:
        db_status = {
            'connected': False,
            'error': str(e)
        }

    return render_template('index.html', db_status=db_status)


@app.route('/api/query', methods=['POST'])
def query():
    """处理用户查询请求"""
    start_time = time.time()  # 记录开始时间

    try:
        data = request.json
        question = data.get('question', '').strip()
        clarification_answer = data.get('clarification_answer')

        if not question:
            return jsonify({
                'success': False,
                'error': '问题不能为空'
            }), 400

        # 安全检查
        MAX_INPUT_LENGTH = 2000
        if len(question) > MAX_INPUT_LENGTH:
            return jsonify({
                'success': False,
                'error': f'输入过长，请控制在{MAX_INPUT_LENGTH}个字符以内'
            }), 400

        session_id = session.get('session_id')
        user_id = session.get('user_id', 'web_user')

        # 获取对话历史
        conversation_history = sessions_store.get(session_id, {}).get('history', [])

        # 执行查询
        result = run_query(
            question=question,
            session_id=session_id,
            user_id=user_id,
            clarification_answer=clarification_answer,
            conversation_history=conversation_history
        )

        # 更新对话历史
        updated_history = result.get('dialog_history', [])
        if session_id not in sessions_store:
            sessions_store[session_id] = {}
        sessions_store[session_id]['history'] = updated_history

        # 检查是否需要澄清
        if result.get('needs_clarification'):
            # 澄清不计入统计（等待用户回答）
            return jsonify({
                'success': True,
                'needs_clarification': True,
                'clarification_question': result.get('clarification_question'),
                'clarification_options': result.get('clarification_options', []),
                'clarification_count': result.get('clarification_count', 1)
            })

        # 检查是否是聊天响应
        is_chat_response = result.get('is_chat_response', False)

        # 计算响应时间
        response_time = time.time() - start_time

        if is_chat_response:
            # 记录聊天查询（总是成功）
            stats_tracker.record_query(
                question=question,
                success=True,
                response_time=response_time,
                is_clarification=False
            )

            return jsonify({
                'success': True,
                'is_chat': True,
                'answer': result.get('chat_response', result.get('answer', '')),
                'sql': None,
                'result': None
            })

        # SQL查询响应
        execution_result = result.get('execution_result', {})
        success = execution_result.get('ok', False)

        # 记录查询统计
        stats_tracker.record_query(
            question=question,
            success=success,
            response_time=response_time,
            is_clarification=clarification_answer is not None,
            error=execution_result.get('error') if not success else None
        )

        if not success:
            return jsonify({
                'success': False,
                'error': execution_result.get('error', '查询执行失败')
            })

        # 构造响应
        response = {
            'success': True,
            'is_chat': False,
            'sql': result.get('candidate_sql', ''),
            'result': {
                'columns': execution_result.get('columns', []),
                'rows': execution_result.get('rows', []),
                'row_count': execution_result.get('row_count', 0)
            },
            'answer': result.get('answer', ''),
            'error': None
        }

        return jsonify(response)

    except Exception as e:
        import traceback
        traceback.print_exc()

        # 记录失败的查询
        response_time = time.time() - start_time
        stats_tracker.record_query(
            question=data.get('question', ''),
            success=False,
            response_time=response_time,
            error=str(e)
        )

        return jsonify({
            'success': False,
            'error': f'服务器错误：{str(e)}'
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据（真实数据）"""
    try:
        stats = stats_tracker.get_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """获取查询历史"""
    try:
        session_id = session.get('session_id')

        if not session_id or session_id not in sessions_store:
            return jsonify([])

        history = sessions_store[session_id].get('history', [])

        # 转换为前端需要的格式
        history_items = []
        for idx, item in enumerate(reversed(history[-20:])):
            if item.get('role') == 'user':
                history_items.append({
                    'id': idx,
                    'question': item.get('content', ''),
                    'timestamp': item.get('timestamp', '')
                })

        return jsonify(history_items)

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/clear_history', methods=['POST'])
def clear_history():
    """清空历史记录"""
    try:
        session_id = session.get('session_id')

        if session_id and session_id in sessions_store:
            sessions_store[session_id]['history'] = []

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/reset_stats', methods=['POST'])
def reset_stats():
    """重置统计数据"""
    try:
        stats_tracker.reset_stats()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    try:
        tables = db_client.get_table_names()

        return jsonify({
            'status': 'healthy',
            'database': {
                'connected': True,
                'name': db_client.database,
                'tables_count': len(tables)
            }
        })

    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


# ==========================================
# 数据库管理 API
# ==========================================
from database_manager import db_manager


@app.route('/api/databases', methods=['GET'])
def get_databases():
    """获取所有数据库配置"""
    try:
        databases = db_manager.get_all_databases()
        current_db = db_manager.get_current_database()

        return jsonify({
            'success': True,
            'databases': databases,
            'current': current_db['id'] if current_db else None
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/databases/current', methods=['GET'])
def get_current_database():
    """获取当前数据库信息"""
    try:
        current_db = db_manager.get_current_database()

        if not current_db:
            return jsonify({
                'success': False,
                'error': '未找到当前数据库配置'
            }), 404

        # 获取实际连接信息
        try:
            tables = db_client.get_table_names()
            current_db['tables_count'] = len(tables)
            current_db['connected'] = True
        except:
            current_db['tables_count'] = 0
            current_db['connected'] = False

        return jsonify({
            'success': True,
            'database': current_db
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/databases/switch', methods=['POST'])
def switch_database():
    """切换数据库"""
    try:
        data = request.json
        db_id = data.get('database_id')

        if not db_id:
            return jsonify({
                'success': False,
                'error': '缺少 database_id 参数'
            }), 400

        # 获取数据库配置
        db_config = db_manager.get_database(db_id)
        if not db_config:
            return jsonify({
                'success': False,
                'error': f'数据库不存在：{db_id}'
            }), 404

        # 切换数据库
        if db_manager.switch_database(db_id):
            # 重新初始化数据库客户端
            global db_client
            from tools.db import DatabaseClient

            db_client = DatabaseClient(
                host=db_config['host'],
                port=db_config['port'],
                user=db_config['user'],
                password=db_config.get('password', ''),
                database=db_config['name']
            )

            # 重新生成 schema
            from tools.schema_manager import SchemaManager
            schema_manager = SchemaManager()
            schema_manager.extract_schema()

            return jsonify({
                'success': True,
                'message': f'已切换到数据库：{db_config["display_name"]}',
                'database': db_config
            })
        else:
            return jsonify({
                'success': False,
                'error': '切换失败'
            }), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'切换失败：{str(e)}'
        }), 500


@app.route('/api/databases', methods=['POST'])
def add_database():
    """添加新数据库"""
    try:
        data = request.json

        # 验证必填字段
        required_fields = ['id', 'name', 'display_name', 'host', 'port', 'user']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必填字段：{field}'
                }), 400

        # 测试连接
        test_result = db_manager.test_connection(data)
        if not test_result['success']:
            return jsonify({
                'success': False,
                'error': test_result['message']
            }), 400

        # 添加数据库
        if db_manager.add_database(data):
            return jsonify({
                'success': True,
                'message': '数据库添加成功',
                'tables_count': test_result['tables_count']
            })
        else:
            return jsonify({
                'success': False,
                'error': '数据库添加失败'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/databases/<db_id>', methods=['PUT'])
def update_database(db_id):
    """更新数据库配置"""
    try:
        data = request.json

        if db_manager.update_database(db_id, data):
            return jsonify({
                'success': True,
                'message': '数据库更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '数据库不存在'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/databases/<db_id>', methods=['DELETE'])
def delete_database(db_id):
    """删除数据库配置"""
    try:
        if db_manager.delete_database(db_id):
            return jsonify({
                'success': True,
                'message': '数据库删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法删除数据库（可能是当前使用的数据库）'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/databases/test', methods=['POST'])
def test_database_connection():
    """测试数据库连接"""
    try:
        data = request.json
        result = db_manager.test_connection(data)

        return jsonify(result)

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'测试失败：{str(e)}'
        }), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 NL2SQL Web 应用启动中...")
    print("=" * 60)
    print(f"📍 访问地址: http://localhost:5000")
    print(f"📊 仪表盘: http://localhost:5000")
    print(f"💡 提示: 按 Ctrl+C 停止服务器")
    print("=" * 60)

    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000,
        threaded=True
    )