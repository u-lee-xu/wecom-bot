#!/usr/bin/env python3
"""
测试文件处理功能
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from file_downloader import file_downloader
from file_processor import file_processor

async def test_text_file():
    """测试文本文件处理"""
    print("=" * 60)
    print("测试：文本文件处理")
    print("=" * 60)

    # 创建一个测试文本文件
    test_file = "test_sample.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("""
这是一个测试文件。

文件内容包括：
1. 标题：企业微信智能机器人测试
2. 作者：iFlow CLI
3. 内容：这是用于测试文件处理功能的示例文本。

文件处理功能应该能够：
- 读取文本内容
- 保留格式
- 传递给 AI 进行分析

测试结束。
""")

    print(f"\n[步骤 1] 创建测试文件: {test_file}")

    # 处理文件
    result = await file_processor.process_file(test_file, "file")

    print("\n[结果]")
    print(f"成功: {result['success']}")
    print(f"文件信息: {result['file_info']}")
    print(f"内容预览:\n{result['content'][:200]}...")

    # 清理
    os.remove(test_file)
    print(f"\n✓ 测试文件已清理")

    return result['success']

async def test_document_file():
    """测试文档文件处理"""
    print("\n" + "=" * 60)
    print("测试：文档文件处理")
    print("=" * 60)

    # 创建一个测试文档文件（模拟）
    test_file = "test_sample.md"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("""
# 测试文档

## 概述
这是一个 Markdown 格式的测试文档。

## 功能
1. 支持多种文件格式
2. 自动提取文本内容
3. 传递给 AI 分析

## 测试数据
- 文件类型: Markdown
- 编码: UTF-8
- 内容长度: 简短

## 结论
文件处理功能正常工作。
""")

    print(f"\n[步骤 1] 创建测试文档: {test_file}")

    # 处理文件
    result = await file_processor.process_file(test_file, "file")

    print("\n[结果]")
    print(f"成功: {result['success']}")
    print(f"文件信息: {result['file_info']}")
    print(f"内容预览:\n{result['content'][:200]}...")

    # 清理
    os.remove(test_file)
    print(f"\n✓ 测试文件已清理")

    return result['success']

async def test_image_file():
    """测试图片文件处理"""
    print("\n" + "=" * 60)
    print("测试：图片文件处理")
    print("=" * 60)

    # 创建一个简单的测试图片（文本文件模拟）
    test_file = "test_image.jpg"
    with open(test_file, 'wb') as f:
        # 写入一些模拟数据
        f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $. \' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?')

    print(f"\n[步骤 1] 创建测试图片: {test_file}")

    # 处理文件
    result = await file_processor.process_file(test_file, "image")

    print("\n[结果]")
    print(f"成功: {result['success']}")
    print(f"文件信息: {result['file_info']}")
    print(f"内容:\n{result['content']}")

    # 清理
    os.remove(test_file)
    print(f"\n✓ 测试文件已清理")

    return result['success']

async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始测试文件处理功能")
    print("=" * 60)

    # 测试 1：文本文件
    test1_passed = await test_text_file()

    # 测试 2：文档文件
    test2_passed = await test_document_file()

    # 测试 3：图片文件
    test3_passed = await test_image_file()

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"测试 1 (文本文件): {'✓ 通过' if test1_passed else '✗ 失败'}")
    print(f"测试 2 (文档文件): {'✓ 通过' if test2_passed else '✗ 失败'}")
    print(f"测试 3 (图片文件): {'✓ 通过' if test3_passed else '✗ 失败'}")

    if test1_passed and test2_passed and test3_passed:
        print("\n✓ 所有测试通过！文件处理功能正常。")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查代码。")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)