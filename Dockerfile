# 个人智能工作台 · Web 界面镜像（Railway / Fly.io / 自建服务器通用）
FROM python:3.11-slim

WORKDIR /app

# 先装依赖，充分利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝源码与配置
COPY app.py .
COPY .streamlit/ .streamlit/
COPY workbench/ workbench/
COPY config/ config/

# 运行数据目录（挂载持久卷时可覆盖）
RUN mkdir -p /app/data

EXPOSE 8501

# 健康检查（用 Python 内置 urllib，避免额外装 curl）
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=5)" || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
