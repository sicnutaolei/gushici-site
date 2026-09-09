FROM python:3.12-slim

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

# 数据目录（SQLite 数据库存放处，可通过 volume 持久化）
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# 时区：影响「每日一诗」按天切换，默认东八区，可在 docker-compose 中覆盖
ENV TZ=Asia/Shanghai
ENV SECRET_KEY=please-change-this-secret-key
EXPOSE 5000

CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "--timeout", "60", "app:app"]
