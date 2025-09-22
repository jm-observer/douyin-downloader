# 使用官方Python 3.11镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # 日志级别
    LOG_LEVEL=DEBUG \
    # 显示详细输出
    VERBOSE=1 \
    # Docker环境标识
    DOCKER_CONTAINER=true \
    # 无头模式
    HEADLESS=true

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    # 基础工具
    curl \
    wget \
    git \
    # 网络工具
    ca-certificates \
    # 调试工具
    procps \
    net-tools \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/* \
    # 显示安装信息
    && echo "✅ 系统依赖安装完成"

# 复制requirements.txt并安装Python依赖
COPY requirements.txt .
RUN echo "📦 开始安装Python依赖..." && \
    pip install --no-cache-dir -r requirements.txt && \
    echo "✅ Python依赖安装完成"

# 安装Playwright（用于自动获取Cookie）
RUN echo "🎭 开始安装Playwright..." && \
    pip install playwright && \
    echo "🌐 安装Chromium浏览器..." && \
    playwright install chromium && \
    echo "🔧 安装Chromium依赖..." && \
    playwright install-deps chromium && \
    echo "✅ Playwright安装完成"

# 创建下载目录
RUN mkdir -p /app/Downloaded && \
    echo "📁 创建下载目录: /app/Downloaded"

# 复制项目文件
COPY . .
RUN echo "📋 项目文件复制完成"

# 设置权限
RUN chmod +x *.py && \
    echo "🔐 设置文件执行权限完成"

# 显示环境信息
RUN echo "🔍 环境信息:" && \
    echo "  - Python版本: $(python --version)" && \
    echo "  - 工作目录: $(pwd)" && \
    echo "  - 文件列表:" && \
    ls -la && \
    echo "  - 网络测试:" && \
    curl -s --connect-timeout 5 https://www.douyin.com > /dev/null && echo "    ✅ 网络连接正常" || echo "    ❌ 网络连接失败"

# 暴露端口（如果需要的话）
# EXPOSE 8000

# 设置默认命令
CMD ["python", "--version"]
