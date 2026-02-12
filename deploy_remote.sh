#!/bin/bash

################################################################################
# 企业微信智能机器人 - 远程部署脚本
# 用途：在新设备上自动部署企业微信机器人
# 使用方法：bash deploy_remote.sh
################################################################################

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# 检查是否以 root 权限运行
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "请勿以 root 用户运行此脚本。使用普通用户运行即可。"
    fi
}

# 检查必要的命令
check_dependencies() {
    info "检查系统依赖..."

    local commands=("python3" "pip3" "curl" "systemctl")
    for cmd in "${commands[@]}"; do
        if ! command -v $cmd &> /dev/null; then
            error "缺少必要命令: $cmd"
        fi
    done

    info "系统依赖检查通过"
}

# 检查 Python 版本
check_python_version() {
    info "检查 Python 版本..."

    local python_version=$(python3 --version 2>&1 | awk '{print $2}')
    local major=$(echo $python_version | cut -d. -f1)
    local minor=$(echo $python_version | cut -d. -f2)

    if [[ $major -lt 3 ]] || [[ $major -eq 3 && $minor -lt 8 ]]; then
        error "Python 版本过低 ($python_version)，需要 Python 3.8 或更高版本"
    fi

    info "Python 版本: $python_version ✓"
}

# 安装 iFlow CLI
install_iflow() {
    info "检查 iFlow CLI..."

    if ! command -v iflow &> /dev/null; then
        warn "iFlow CLI 未安装，正在安装..."

        if command -v npx &> /dev/null; then
            # 使用 npx 安装（推荐）
            info "使用 npx 安装 iFlow CLI..."
            npx -y @iflow/cli latest
        else
            # 使用 bash 安装脚本
            info "使用安装脚本安装 iFlow CLI..."
            bash -c "$(curl -fsSL https://gitee.com/iflow-ai/iflow-cli/raw/main/install.sh)"
        fi

        info "iFlow CLI 安装完成"
    else
        info "iFlow CLI 已安装 ✓"
    fi

    # 检查是否需要配置 API key
    if ! iflow config get apiKey &> /dev/null; then
        warn "iFlow API key 未配置"
        echo ""
        read -p "请输入 iFlow API key (留空跳过): " api_key

        if [[ -n "$api_key" ]]; then
            iflow config set apiKey "$api_key"
            iflow config set searchApiKey "$api_key"
            info "iFlow API key 配置完成"
        else
            warn "跳过 API key 配置，稍后手动配置: iflow config set apiKey YOUR_KEY"
        fi
    else
        info "iFlow API key 已配置 ✓"
    fi
}

# 创建项目目录
create_project_dir() {
    local install_dir="${1:-/opt/wecom-bot}"

    info "创建项目目录: $install_dir"

    if [[ ! -d "$install_dir" ]]; then
        sudo mkdir -p "$install_dir"
        sudo chown $USER:$USER "$install_dir"
    fi

    cd "$install_dir"
    info "当前目录: $(pwd)"
}

# 解压部署包
extract_package() {
    local package_file="${1:-/tmp/wecom-bot-deploy.tar.gz}"

    info "解压部署包: $package_file"

    if [[ ! -f "$package_file" ]]; then
        error "部署包不存在: $package_file"
    fi

    tar -xzf "$package_file"
    info "部署包解压完成"
}

# 创建虚拟环境
create_venv() {
    info "创建 Python 虚拟环境..."

    if [[ -d "venv" ]]; then
        warn "虚拟环境已存在，跳过创建"
    else
        python3 -m venv venv
        info "虚拟环境创建完成"
    fi
}

# 安装 Python 依赖
install_dependencies() {
    info "安装 Python 依赖..."

    if [[ ! -f "requirements.txt" ]]; then
        error "requirements.txt 不存在"
    fi

    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    deactivate

    info "Python 依赖安装完成"
}

# 配置文件检查
check_config() {
    info "检查配置文件..."

    if [[ ! -f "config.py" ]]; then
        error "config.py 不存在"
    fi

    # 检查配置是否已修改（不是示例配置）
    if grep -q "your_token_here" config.py || grep -q "your_corp_id_here" config.py; then
        warn "config.py 包含示例配置，请修改为实际配置"
        echo ""
        read -p "是否现在编辑配置文件? (y/n): " edit_config

        if [[ "$edit_config" == "y" || "$edit_config" == "Y" ]]; then
            ${EDITOR:-nano} config.py
        else
            warn "请稍后手动编辑 config.py 文件"
        fi
    else
        info "配置文件检查通过 ✓"
    fi
}

# 创建必要目录
create_directories() {
    info "创建必要目录..."

    mkdir -p user_data shared_files downloads

    info "目录创建完成"
}

# 安装 systemd 服务
install_service() {
    info "安装 systemd 服务..."

    if [[ ! -f "wecom-bot.service" ]]; then
        error "wecom-bot.service 文件不存在"
    fi

    # 更新服务文件中的路径
    local current_dir=$(pwd)
    local username=$USER

    sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$current_dir|" wecom-bot.service
    sudo sed -i "s|User=.*|User=$username|" wecom-bot.service
    sudo sed -i "s|ExecStart=.*|ExecStart=$current_dir/venv/bin/python app.py|" wecom-bot.service

    # 安装服务文件
    sudo cp wecom-bot.service /etc/systemd/system/

    # 重载 systemd
    sudo systemctl daemon-reload

    info "systemd 服务安装完成"
}

# 启动服务
start_service() {
    info "启用并启动服务..."

    sudo systemctl enable wecom-bot.service
    sudo systemctl start wecom-bot.service

    sleep 2

    # 检查服务状态
    if sudo systemctl is-active --quiet wecom-bot.service; then
        info "服务启动成功 ✓"
    else
        error "服务启动失败，请检查日志: sudo journalctl -u wecom-bot.service -f"
    fi
}

# 显示部署完成信息
show_summary() {
    echo ""
    echo "======================================"
    info "部署完成！"
    echo "======================================"
    echo ""
    echo "常用命令："
    echo "  查看服务状态: sudo systemctl status wecom-bot.service"
    echo "  启动服务:     sudo systemctl start wecom-bot.service"
    echo "  停止服务:     sudo systemctl stop wecom-bot.service"
    echo "  重启服务:     sudo systemctl restart wecom-bot.service"
    echo "  查看日志:     sudo journalctl -u wecom-bot.service -f"
    echo ""
    echo "配置文件位置: $(pwd)/config.py"
    echo "数据库位置:   $(pwd)/wecom_bot.db"
    echo "用户数据:     $(pwd)/user_data/"
    echo ""
    warn "请确保："
    echo "  1. 企业微信后台的回调 URL 配置正确"
    echo "  2. config.py 中的配置已填写正确"
    echo "  3. 防火墙已开放对应端口"
    echo ""
}

# 主函数
main() {
    echo "======================================"
    echo "企业微信智能机器人 - 远程部署脚本"
    echo "======================================"
    echo ""

    # 参数解析
    local package_file=""
    local install_dir="/opt/wecom-bot"

    while [[ $# -gt 0 ]]; do
        case $1 in
            -p|--package)
                package_file="$2"
                shift 2
                ;;
            -d|--dir)
                install_dir="$2"
                shift 2
                ;;
            -h|--help)
                echo "用法: $0 [选项]"
                echo ""
                echo "选项:"
                echo "  -p, --package FILE   部署包路径 (默认: /tmp/wecom-bot-deploy.tar.gz)"
                echo "  -d, --dir DIR        安装目录 (默认: /opt/wecom-bot)"
                echo "  -h, --help           显示此帮助信息"
                echo ""
                exit 0
                ;;
            *)
                error "未知选项: $1"
                ;;
        esac
    done

    # 执行部署步骤
    check_root
    check_dependencies
    check_python_version
    install_iflow
    create_project_dir "$install_dir"

    if [[ -n "$package_file" ]]; then
        extract_package "$package_file"
    else
        warn "未指定部署包，跳过解压步骤"
    fi

    create_venv
    install_dependencies
    check_config
    create_directories
    install_service
    start_service
    show_summary
}

# 运行主函数
main "$@"