"""
数据库配置管理器
支持多数据库配置的保存、加载和切换
"""
import json
import os
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
                    'password': '',  # 从环境变量读取
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
        """
        添加新数据库配置

        Args:
            config: 数据库配置字典，必须包含：
                - id: 唯一标识符
                - name: 数据库名称
                - display_name: 显示名称
                - host: 主机地址
                - port: 端口
                - user: 用户名
                - password: 密码
                - icon: 图标（可选）
                - description: 描述（可选）

        Returns:
            bool: 是否添加成功
        """
        # 验证必填字段
        required_fields = ['id', 'name', 'display_name', 'host', 'port', 'user']
        for field in required_fields:
            if field not in config:
                print(f"缺少必填字段：{field}")
                return False

        # 检查ID是否已存在
        if self.get_database(config['id']):
            print(f"数据库ID已存在：{config['id']}")
            return False

        # 添加默认值
        if 'icon' not in config:
            config['icon'] = '🗄️'
        if 'description' not in config:
            config['description'] = ''
        if 'is_default' not in config:
            config['is_default'] = False

        # 添加到配置
        self.configs['databases'].append(config)
        self._save_configs()

        return True

    def update_database(self, db_id: str, config: Dict) -> bool:
        """更新数据库配置"""
        databases = self.configs.get('databases', [])

        for i, db in enumerate(databases):
            if db['id'] == db_id:
                # 保留ID不变
                config['id'] = db_id
                databases[i] = {**db, **config}
                self.configs['databases'] = databases
                self._save_configs()
                return True

        return False

    def delete_database(self, db_id: str) -> bool:
        """删除数据库配置"""
        # 不能删除当前使用的数据库
        if db_id == self.current_db:
            print("不能删除当前使用的数据库")
            return False

        databases = self.configs.get('databases', [])
        databases = [db for db in databases if db['id'] != db_id]

        if len(databases) == len(self.configs['databases']):
            return False  # 没有找到要删除的数据库

        self.configs['databases'] = databases
        self._save_configs()

        return True

    def switch_database(self, db_id: str) -> bool:
        """切换当前数据库"""
        # 检查数据库是否存在
        db = self.get_database(db_id)
        if not db:
            print(f"数据库不存在：{db_id}")
            return False

        # 切换当前数据库
        self.current_db = db_id
        self.configs['current'] = db_id
        self._save_configs()

        return True

    def test_connection(self, config: Dict) -> Dict:
        """
        测试数据库连接

        Returns:
            dict: {'success': bool, 'message': str, 'tables_count': int}
        """
        try:
            # 动态导入以避免循环依赖
            from tools.db import DatabaseClient

            # 创建临时客户端
            temp_client = DatabaseClient(
                host=config['host'],
                port=config['port'],
                user=config['user'],
                password=config.get('password', ''),
                database=config['name']
            )

            # 测试连接
            if temp_client.test_connection():
                tables = temp_client.get_table_names()
                return {
                    'success': True,
                    'message': '连接成功',
                    'tables_count': len(tables)
                }
            else:
                return {
                    'success': False,
                    'message': '连接失败',
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