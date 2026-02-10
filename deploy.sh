#!/bin/bash
# 企业微信机器人部署脚本

set -e  # 遇到错误立即退出

echo "========================================="
echo "企业微信机器人部署脚本"
echo "========================================="

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
    echo "错误：请不要使用 root 用户运行此脚本"
    exit 1
fi

# 1. 检查虚拟环境
echo ""
echo "[步骤 1/6] 检查虚拟环境..."
if [ ! -d "venv" ]; then
    echo "虚拟环境不存在，正在创建..."
    python3 -m venv venv
    echo "✓ 虚拟环境创建成功"
else
    echo "✓ 虚拟环境已存在"
fi

# 2. 激活虚拟环境并安装依赖
echo ""
echo "[步骤 2/6] 安装依赖..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ 依赖安装完成"

# 3. 检查配置文件
echo ""
echo "[步骤 3/6] 检查配置文件..."
if grep -q "your_token_here" config.py; then
    echo "⚠ 警告：config.py 中的企业微信配置尚未填写"
    echo "  请编辑 config.py，填写以下信息："
    echo "  - WECOM_TOKEN"
    echo "  - WECOM_ENCODING_AES_KEY"
    echo ""
    read -p "是否现在编辑配置文件？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        nano config.py
    fi
else
    echo "✓ 配置文件已填写"
fi

# 4. 创建必要的目录
echo ""
echo "[步骤 4/6] 创建必要的目录..."
mkdir -p downloads
mkdir -p logs
echo "✓ 目录创建完成"

# 5. 配置防火墙
echo ""
echo "[步骤 5/6] 检查防火墙配置..."
if command -v ufw &> /dev/null; then
    echo "检测到 ufw 防火墙"
    if sudo ufw status | grep -q "5000"; then
        echo "✓ 端口 5000 已开放"
    else
        echo "正在开放端口 5000..."
        sudo ufw allow 5000
        echo "✓ 端口 5000 已开放"
    fi
else
    echo "⚠ 未检测到 ufw 防火墙，跳过防火墙配置"
fi

# 6. 安装 systemd 服务
echo ""
echo "[步骤 6/6] 配置 systemd 服务..."
SERVICE_FILE="/etc/systemd/system/wecom-bot.service"
if [ -f "$SERVICE_FILE" ]; then
    echo "✓ systemd 服务已存在"
    read -p "是否重新安装服务？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl stop wecom-bot
        sudo systemctl disable wecom-bot
        sudo rm -f "$SERVICE_FILE"
        echo "旧服务已删除"
        INSTALL_SERVICE=1
    else
        INSTALL_SERVICE=0
    fi
else
    INSTALL_SERVICE=1
fi

if [ $INSTALL_SERVICE -eq 1 ]; then
    echo "正在安装 systemd 服务..."
    sudo cp wecom-bot.service "$SERVICE_FILE"
    sudo systemctl daemon-reload
    sudo systemctl enable wecom-bot
    echo "✓ systemd 服务安装完成"
fi

# 完成
echo ""
echo "========================================="
echo "部署完成！"
echo "========================================="
echo ""
echo "接下来的步骤："
echo ""
echo "1. 确保已填写 config.py 中的企业微信配置"
echo ""
echo "2. 在企业微信后台设置回调 URL："
echo "   http://$(hostname -I | awk '{print $1}'):5000/callback"
echo ""
echo "3. 启动服务："
echo "   sudo systemctl start wecom-bot"
echo ""
echo "4. 查看服务状态："
echo "   sudo systemctl status wecom-bot"
echo ""
echo "5. 查看日志："
echo "   sudo journalctl -u wecom-bot -f"
echo ""
echo "6. 停止服务："
echo "   sudo systemctl stop wecom-bot"
echo ""
echo "7. 重启服务："
echo "   sudo systemctl restart wecom-bot"
echo ""
echo "========================================="