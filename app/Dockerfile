# 使用 DaoCloud（道客）DockerHub 镜像加速源
# 如果你的群晖 Docker 已配置 DaoCloud 加速，也可改为官方镜像: python:3.11-slim
FROM docker.m.daocloud.io/library/python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# -u 关闭 stdout 块缓冲，否则容器内日志会滞留数小时才落盘
CMD ["python", "-u", "main.py"]
