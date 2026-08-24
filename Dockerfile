FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY main.py .
COPY src/ ./src/

# 创建非 root 用户
RUN useradd -m -u 1000 botuser \
    && mkdir -p /data \
    && chown -R botuser:botuser /app /data
USER botuser

ENV DATA_DIR=/data \
    DROP_PENDING_UPDATES=false

VOLUME ["/data"]

# 运行
CMD ["python", "main.py"]
