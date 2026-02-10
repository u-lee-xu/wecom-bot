#!/usr/bin/env python3
"""
测试会话记忆功能
验证重启后是否能恢复历史会话
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from session_manager import session_manager
from database import db_manager

async def test_session_memory():
    """测试会话记忆功能"""
    print("=" * 60)
    print("测试：会话记忆功能")
    print("=" * 60)

    test_user_id = "test_user_123"

    # 步骤 1：清理旧数据
    print("\n[步骤 1] 清理旧数据...")
    try:
        import sqlite3
        conn = sqlite3.connect("wecom_bot.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (test_user_id,))
        cursor.execute("DELETE FROM messages WHERE user_id = ?", (test_user_id,))
        conn.commit()
        conn.close()
        print("✓ 旧数据已清理")
    except Exception as e:
        print(f"⚠ 清理数据失败: {e}")

    # 步骤 2：模拟第一次会话
    print("\n[步骤 2] 模拟第一次会话（创建新会话）...")
    client1 = await session_manager.get_or_create_session(test_user_id)
    print(f"✓ 会话创建成功，当前会话数: {session_manager.get_session_count()}")

    # 检查数据库
    saved_session_id = db_manager.get_user_session(test_user_id)
    print(f"✓ 数据库中的 session_id: {saved_session_id}")

    # 记录一条消息
    db_manager.log_message(test_user_id, "user_message", "第一条测试消息")
    print("✓ 已记录消息到数据库")

    # 步骤 3：模拟重启（清空内存中的 sessions）
    print("\n[步骤 3] 模拟重启（清空内存中的 sessions）...")
    session_manager.sessions.clear()
    print(f"✓ 内存中的 sessions 已清空，当前会话数: {session_manager.get_session_count()}")

    # 步骤 4：模拟第二次会话（应该恢复之前的会话）
    print("\n[步骤 4] 模拟第二次会话（应该恢复历史会话）...")
    client2 = await session_manager.get_or_create_session(test_user_id)
    print(f"✓ 会话恢复成功，当前会话数: {session_manager.get_session_count()}")

    # 检查恢复的 session_id 是否一致
    restored_session_id = db_manager.get_user_session(test_user_id)
    print(f"✓ 恢复的 session_id: {restored_session_id}")

    # 验证
    print("\n[验证]")
    if saved_session_id == restored_session_id:
        print(f"✓ 测试通过！session_id 一致: {saved_session_id}")
        print("✓ 会话记忆功能正常工作，重启后可以恢复历史会话")
        return True
    else:
        print(f"✗ 测试失败！session_id 不一致")
        print(f"  之前: {saved_session_id}")
        print(f"  恢复: {restored_session_id}")
        return False

async def test_multi_user_isolation():
    """测试多用户会话隔离"""
    print("\n" + "=" * 60)
    print("测试：多用户会话隔离")
    print("=" * 60)

    user_a = "user_A"
    user_b = "user_B"

    print("\n[步骤 1] 创建两个用户的会话...")
    client_a = await session_manager.get_or_create_session(user_a)
    client_b = await session_manager.get_or_create_session(user_b)

    session_id_a = db_manager.get_user_session(user_a)
    session_id_b = db_manager.get_user_session(user_b)

    print(f"✓ 用户 A 的 session_id: {session_id_a}")
    print(f"✓ 用户 B 的 session_id: {session_id_b}")

    print("\n[验证]")
    if session_id_a != session_id_b:
        print("✓ 测试通过！两个用户的 session_id 不同")
        print("✓ 多用户会话隔离正常工作")
        return True
    else:
        print("✗ 测试失败！两个用户的 session_id 相同")
        return False

async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始测试会话管理功能")
    print("=" * 60)

    # 测试 1：会话记忆
    test1_passed = await test_session_memory()

    # 测试 2：多用户隔离
    test2_passed = await test_multi_user_isolation()

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"测试 1 (会话记忆): {'✓ 通过' if test1_passed else '✗ 失败'}")
    print(f"测试 2 (多用户隔离): {'✓ 通过' if test2_passed else '✗ 失败'}")

    if test1_passed and test2_passed:
        print("\n✓ 所有测试通过！会话管理功能正常。")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查代码。")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)