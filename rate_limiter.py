"""
限流保护器
防止用户频繁调用
"""

import time
from typing import Dict, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """限流保护器"""

    def __init__(self, max_requests: int = 10, time_window: int = 60):
        """
        初始化限流器

        Args:
            max_requests: 时间窗口内最大请求数
            time_window: 时间窗口（秒）
        """
        self.max_requests = max_requests
        self.time_window = time_window
        # 用户 ID 到请求时间列表的映射
        self.user_requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, user_id: str) -> tuple[bool, Optional[int]]:
        """
        检查是否允许请求

        Args:
            user_id: 用户 ID

        Returns:
            (是否允许, 剩余等待秒数)
        """
        current_time = time.time()
        user_request_times = self.user_requests[user_id]

        # 移除时间窗口外的请求记录
        user_request_times = [
            t for t in user_request_times
            if current_time - t < self.time_window
        ]
        self.user_requests[user_id] = user_request_times

        # 检查是否超过限制
        if len(user_request_times) >= self.max_requests:
            # 计算最早请求的剩余时间
            oldest_request = min(user_request_times)
            wait_time = int(self.time_window - (current_time - oldest_request)) + 1
            logger.warning(f"[限流] 用户 {user_id} 超过限制，需等待 {wait_time} 秒")
            return False, wait_time

        # 允许请求，记录时间
        user_request_times.append(current_time)
        logger.info(f"[限流] 用户 {user_id} 请求通过，当前请求数: {len(user_request_times)}")
        return True, None

    def reset_user(self, user_id: str):
        """重置用户的请求记录"""
        if user_id in self.user_requests:
            del self.user_requests[user_id]
            logger.info(f"[限流] 用户 {user_id} 请求记录已重置")

    def get_user_request_count(self, user_id: str) -> int:
        """获取用户当前请求数"""
        current_time = time.time()
        user_request_times = self.user_requests[user_id]
        # 只计算时间窗口内的请求
        user_request_times = [
            t for t in user_request_times
            if current_time - t < self.time_window
        ]
        return len(user_request_times)


# 全局限流器实例
rate_limiter = RateLimiter(max_requests=10, time_window=60)