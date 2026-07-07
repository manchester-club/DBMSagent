#!/bin/bash
# 安装 Node.js 脚本

set -e

echo "=========================================="
echo "Node.js 安装脚本"
echo "=========================================="
echo ""

# 检查是否已安装
if command -v node &> /dev/null; then
    echo "✅ Node.js 已安装"
    node --version
    npm --version
    exit 0
fi

echo "检测到 Node.js 未安装，开始安装..."
echo ""

# 方法1: 使用 nvm（推荐）
if [ -d "$HOME/.nvm" ]; then
    echo "检测到 nvm 已安装，使用 nvm..."
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    nvm install 18
    nvm use 18
    echo "✅ Node.js 安装完成"
    node --version
    npm --version
    exit 0
fi

# 方法2: 下载预编译版本
echo "使用预编译版本安装..."
NODE_VERSION="v18.20.0"
INSTALL_DIR="$HOME/.local/nodejs"

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "下载 Node.js ${NODE_VERSION}..."
if [ ! -f "node-${NODE_VERSION}-linux-x64.tar.xz" ]; then
    curl -fsSL "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.xz" \
        -o "node-${NODE_VERSION}-linux-x64.tar.xz" || {
        echo "❌ 下载失败，请检查网络连接"
        exit 1
    }
fi

echo "解压..."
tar -xf "node-${NODE_VERSION}-linux-x64.tar.xz"

# 添加到 PATH
NODE_BIN="$INSTALL_DIR/node-${NODE_VERSION}-linux-x64/bin"
export PATH="$NODE_BIN:$PATH"

# 添加到 .bashrc
if ! grep -q "$NODE_BIN" ~/.bashrc 2>/dev/null; then
    echo "" >> ~/.bashrc
    echo "# Node.js" >> ~/.bashrc
    echo "export PATH=\"$NODE_BIN:\$PATH\"" >> ~/.bashrc
    echo "✅ 已添加到 ~/.bashrc"
fi

echo ""
echo "✅ Node.js 安装完成！"
echo ""
echo "当前会话可以使用："
echo "  export PATH=\"$NODE_BIN:\$PATH\""
echo ""
echo "或重新加载 shell："
echo "  source ~/.bashrc"
echo ""
echo "验证安装："
"$NODE_BIN/node" --version
"$NODE_BIN/npm" --version
