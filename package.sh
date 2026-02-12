#!/bin/bash

################################################################################
# 企业微信智能机器人 - 打包脚本
# 用途：创建部署包，用于在其他设备上部署
# 使用方法：bash package.sh
################################################################################

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 版本信息
VERSION=$(date +%Y%m%d)
PACKAGE_NAME="wecom-bot-v${VERSION}.tar.gz"

# 需要打包的文件
FILES=(
    "app.py"
    "config.py"
    "database.py"
    "session_manager.py"
    "rate_limiter.py"
    "file_downloader.py"
    "file_processor.py"
    "WXBizJsonMsgCrypt.py"
    "ierror.py"
    "requirements.txt"
    "wecom-bot.service"
    "README.md"
    "USER_GUIDE.md"
    "deploy_remote.sh"
)

info "开始打包企业微信机器人..."
info "版本: $VERSION"
info "项目目录: $PROJECT_DIR"

# 创建临时目录
TEMP_DIR=$(mktemp -d)
info "创建临时目录: $TEMP_DIR"

# 复制文件
info "复制文件到临时目录..."
for file in "${FILES[@]}"; do
    if [[ -f "$PROJECT_DIR/$file" ]]; then
        cp "$PROJECT_DIR/$file" "$TEMP_DIR/"
        info "  ✓ $file"
    else
        warn "  ✗ $file (文件不存在，跳过)"
    fi
done

# 打包
info "创建压缩包: $PACKAGE_NAME"
tar -czf "$PROJECT_DIR/$PACKAGE_NAME" -C "$TEMP_DIR" .

# 清理临时目录
rm -rf "$TEMP_DIR"
info "清理临时目录"

# 显示包信息
PACKAGE_SIZE=$(du -h "$PROJECT_DIR/$PACKAGE_NAME" | cut -f1)
echo ""
info "======================================"
info "打包完成！"
info "======================================"
echo ""
echo "包文件: $PROJECT_DIR/$PACKAGE_NAME"
echo "包大小: $PACKAGE_SIZE"
echo ""
echo "部署步骤："
echo "  1. 上传到目标设备: scp $PACKAGE_NAME user@target:/tmp/"
echo "  2. SSH 登录目标设备: ssh user@target"
echo "  3. 运行部署脚本: bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/your-repo/wecom-bot/main/deploy_remote.sh)\" -p /tmp/$PACKAGE_NAME"
echo "  4. 或手动运行: tar -xzf /tmp/$PACKAGE_NAME && cd $(pwd) && bash deploy_remote.sh"
echo ""