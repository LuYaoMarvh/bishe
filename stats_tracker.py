"""
统计追踪模块
用于记录和统计查询信息
"""
import json
import os
from datetime import datetime
from pathlib import Path


class StatsTracker:
    """统计追踪器"""

    def __init__(self, stats_file='data/stats.json'):
        self.stats_file = stats_file
        self.stats = self._load_stats()

    def _load_stats(self):
        """加载统计数据"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载统计数据失败：{e}")
                return self._init_stats()
        return self._init_stats()

    def _init_stats(self):
        """初始化统计数据"""
        return {
            'total_queries': 0,
            'success_queries': 0,
            'failed_queries': 0,
            'clarification_count': 0,
            'total_response_time': 0.0,
            'query_history': [],
            'last_updated': datetime.now().isoformat()
        }

    def _save_stats(self):
        """保存统计数据"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)

            self.stats['last_updated'] = datetime.now().isoformat()

            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存统计数据失败：{e}")

    def record_query(self, question, success=True, response_time=0.0,
                     is_clarification=False, error=None):
        """
        记录一次查询

        Args:
            question: 用户问题
            success: 是否成功
            response_time: 响应时间（秒）
            is_clarification: 是否触发了澄清
            error: 错误信息（如果失败）
        """
        self.stats['total_queries'] += 1

        if success:
            self.stats['success_queries'] += 1
        else:
            self.stats['failed_queries'] += 1

        if is_clarification:
            self.stats['clarification_count'] += 1

        self.stats['total_response_time'] += response_time

        # 记录到历史（保留最近100条）
        self.stats['query_history'].append({
            'question': question,
            'success': success,
            'response_time': response_time,
            'is_clarification': is_clarification,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })

        # 只保留最近100条
        if len(self.stats['query_history']) > 100:
            self.stats['query_history'] = self.stats['query_history'][-100:]

        self._save_stats()

    def get_stats(self):
        """获取统计数据"""
        total = self.stats['total_queries']

        if total == 0:
            return {
                'total_queries': 0,
                'success_rate': 0.0,
                'clarification_count': 0,
                'avg_response_time': 0.0
            }

        success_rate = (self.stats['success_queries'] / total) * 100
        avg_time = self.stats['total_response_time'] / total

        return {
            'total_queries': total,
            'success_rate': round(success_rate, 1),
            'clarification_count': self.stats['clarification_count'],
            'avg_response_time': round(avg_time, 2)
        }

    def reset_stats(self):
        """重置统计数据"""
        self.stats = self._init_stats()
        self._save_stats()


# 全局实例
stats_tracker = StatsTracker()