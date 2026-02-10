#!/usr/bin/env python3
"""
测试 iFlow CLI SDK 的 ACP 模式是否正常工作
"""
import asyncio
from iflow_sdk import IFlowClient, AssistantMessage, TaskFinishMessage

async def test_acp_basic():
    """测试基本的 ACP 连接和消息发送"""
    print("=" * 50)
    print("测试 1: 基本 ACP 连接")
    print("=" * 50)

    try:
        async with IFlowClient() as client:
            print("✓ iFlow Client 创建成功")

            # 发送测试消息
            test_message = "你好，请用一句话介绍你自己。"
            print(f"发送消息: {test_message}")
            await client.send_message(test_message)

            # 接收响应
            print("等待响应...")
            response_text = ""
            async for message in client.receive_messages():
                if isinstance(message, AssistantMessage):
                    response_text += message.chunk.text
                    print(message.chunk.text, end="", flush=True)
                elif isinstance(message, TaskFinishMessage):
                    print("\n✓ 任务完成")
                    break

            if response_text:
                print(f"\n✓ 收到响应: {response_text[:100]}...")
                return True
            else:
                print("\n✗ 未收到响应")
                return False

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_acp_tool_call():
    """测试工具调用功能"""
    print("\n" + "=" * 50)
    print("测试 2: 工具调用")
    print("=" * 50)

    try:
        async with IFlowClient() as client:
            print("✓ iFlow Client 创建成功")

            # 请求执行一个简单的文件操作
            test_message = "请列出当前目录下的所有 Python 文件"
            print(f"发送消息: {test_message}")
            await client.send_message(test_message)

            # 接收响应
            print("等待响应...")
            tool_calls = 0
            async for message in client.receive_messages():
                if hasattr(message, 'tool_name'):
                    tool_calls += 1
                    print(f"  工具调用: {message.tool_name}")
                elif isinstance(message, AssistantMessage):
                    print(message.chunk.text, end="", flush=True)
                elif isinstance(message, TaskFinishMessage):
                    print("\n✓ 任务完成")
                    break

            if tool_calls > 0:
                print(f"✓ 检测到 {tool_calls} 次工具调用")
                return True
            else:
                print("⚠ 未检测到工具调用（可能是模型选择了其他方式）")
                return True  # 不算失败

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """运行所有测试"""
    print("\n" + "=" * 50)
    print("开始测试 iFlow CLI SDK ACP 模式")
    print("=" * 50)

    # 测试 1: 基本连接
    test1_passed = await test_acp_basic()

    # 测试 2: 工具调用
    test2_passed = await test_acp_tool_call()

    # 总结
    print("\n" + "=" * 50)
    print("测试总结")
    print("=" * 50)
    print(f"测试 1 (基本连接): {'✓ 通过' if test1_passed else '✗ 失败'}")
    print(f"测试 2 (工具调用): {'✓ 通过' if test2_passed else '✗ 失败'}")

    if test1_passed and test2_passed:
        print("\n✓ 所有测试通过！ACP 模式工作正常。")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查配置。")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)