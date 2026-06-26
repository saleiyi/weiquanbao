FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY *.py ./
COPY web/ ./web/
COPY platforms/ ./platforms/
COPY tools/ ./tools/

# 创建数据目录
RUN mkdir -p data/exports data/decrypted logs

EXPOSE 8090

CMD ["python", "main.py", "--browser"]
