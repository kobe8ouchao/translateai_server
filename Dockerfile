# 使用 Python 3.11 镜像
FROM python:3.11 AS base

# 设置工作目录
WORKDIR /app

# 创建必要的目录
RUN mkdir upload

# 第一阶段：安装系统依赖
FROM base AS system-deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # ODBC 依赖（用于 pyodbc）
    unixodbc \
    unixodbc-dev \
    # 文档处理相关依赖
    ffmpeg \
    # 清理
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 第二阶段：安装 Python 依赖
FROM system-deps AS python-deps
COPY requirements.txt .
# 设置pip配置，增加网络重试，延长超时时间
RUN pip install --no-cache-dir --upgrade pip && \
    pip config set global.timeout 300 && \
    pip config set global.retries 5 && \
    pip install --no-cache-dir -r requirements.txt

# 最终阶段
FROM python-deps AS final
COPY . .
EXPOSE 8998
CMD ["python", "main.py"]