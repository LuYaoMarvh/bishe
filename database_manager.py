"""
数据库配置管理器（修复版）
兼容多种 DatabaseClient 初始化方式
"""
import json
import os
import pymysql
from pathlib import Path
from typing import Dict, List, Optional


class DatabaseManager:
    """数据库配置管理器"""

    def __init__(self, config_file='data/databases.json'):
        self.config_file = config_file
        self.configs = self._load_configs()
        self.current_db = self._load_current_db()

    def _load_configs(self) -> Dict:
        """加载数据库配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载数据库配置失败：{e}")
                return self._init_default_configs()
        return self._init_default_configs()

    def _init_default_configs(self) -> Dict:
        """初始化默认配置"""
        return {
            'databases': [
                {
                    'id': 'chinook',
                    'name': 'chinook',
                    'display_name': 'Chinook 音乐商店',
                    'icon': '🎵',
                    'host': 'localhost',
                    'port': 3306,
                    'user': 'root',
                    'password': '',
                    'description': '音乐商店示例数据库',
                    'is_default': True
                }
            ],
            'current': 'chinook'
        }

    def _load_current_db(self) -> str:
        """加载当前使用的数据库ID"""
        return self.configs.get('current', 'chinook')

    def _save_configs(self):
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.configs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存数据库配置失败：{e}")

    def get_all_databases(self) -> List[Dict]:
        """获取所有数据库配置"""
        return self.configs.get('databases', [])

    def get_database(self, db_id: str) -> Optional[Dict]:
        """获取指定数据库配置"""
        for db in self.configs.get('databases', []):
            if db['id'] == db_id:
                return db
        return None

    def get_current_database(self) -> Optional[Dict]:
        """获取当前数据库配置"""
        return self.get_database(self.current_db)

    def add_database(self, config: Dict) -> bool:
        """添加新数据库配置"""
        required_fields = ['id', 'name', 'display_name', 'host', 'port', 'user']
        for field in required_fields:
            if field not in config:
                print(f"缺少必填字段：{field}")
                return False

        if self.get_database(config['id']):
            print(f"数据库ID已存在：{config['id']}")
            return False

        if 'icon' not in config:
            config['icon'] = '🗄️'
        if 'description' not in config:
            config['description'] = ''
        if 'is_default' not in config:
            config['is_default'] = False

        self.configs['databases'].append(config)
        self._save_configs()

        return True

    def update_database(self, db_id: str, config: Dict) -> bool:
        """更新数据库配置"""
        databases = self.configs.get('databases', [])

        for i, db in enumerate(databases):
            if db['id'] == db_id:
                config['id'] = db_id
                databases[i] = {**db, **config}
                self.configs['databases'] = databases
                self._save_configs()
                return True

        return False

    def delete_database(self, db_id: str) -> bool:
        """删除数据库配置"""
        if db_id == self.current_db:
            print("不能删除当前使用的数据库")
            return False

        databases = self.configs.get('databases', [])
        databases = [db for db in databases if db['id'] != db_id]

        if len(databases) == len(self.configs['databases']):
            return False

        self.configs['databases'] = databases
        self._save_configs()

        return True

    def switch_database(self, db_id: str) -> bool:
        """切换当前数据库"""
        db = self.get_database(db_id)
        if not db:
            print(f"数据库不存在：{db_id}")
            return False

        self.current_db = db_id
        self.configs['current'] = db_id
        self._save_configs()

        return True

    def test_connection(self, config: Dict) -> Dict:
        """
        测试数据库连接（修复版）
        直接使用 pymysql 测试，不依赖项目的 DatabaseClient

        Returns:
            dict: {'success': bool, 'message': str, 'tables_count': int}
        """
        try:
            # 直接使用 pymysql 进行连接测试
            connection = pymysql.connect(
                host=config['host'],
                port=int(config['port']),
                user=config['user'],
                password=config.get('password', ''),
                database=config['name'],
                charset='utf8mb4',
                connect_timeout=10
            )

            # 测试查询
            with connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                tables_count = len(tables)

            connection.close()

            return {
                'success': True,
                'message': '连接成功',
                'tables_count': tables_count
            }

        except pymysql.err.OperationalError as e:
            error_code = e.args[0] if e.args else 0
            error_msg = e.args[1] if len(e.args) > 1 else str(e)

            # 提供更友好的错误提示
            if error_code == 1045:
                return {
                    'success': False,
                    'message': '用户名或密码错误',
                    'tables_count': 0
                }
            elif error_code == 1049:
                return {
                    'success': False,
                    'message': f'数据库 "{config["name"]}" 不存在',
                    'tables_count': 0
                }
            elif error_code == 2003:
                return {
                    'success': False,
                    'message': f'无法连接到 {config["host"]}:{config["port"]}，请检查MySQL服务',
                    'tables_count': 0
                }
            else:
                return {
                    'success': False,
                    'message': f'连接失败：{error_msg}',
                    'tables_count': 0
                }

        except Exception as e:
            return {
                'success': False,
                'message': f'连接失败：{str(e)}',
                'tables_count': 0
            }

    def get_database_summary(self) -> Dict:
        """获取数据库统计摘要"""
        databases = self.get_all_databases()
        current_db = self.get_current_database()

        return {
            'total_count': len(databases),
            'current_db': {
                'id': current_db['id'] if current_db else None,
                'display_name': current_db['display_name'] if current_db else None,
                'icon': current_db['icon'] if current_db else None
            }
        }


# 全局实例
db_manager = DatabaseManager()