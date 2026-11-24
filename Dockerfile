FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# 构建时只导入自编样例，不打包课程数据。
RUN python -m zhibei.bank.demo && python -m zhibei.bank.importer data/demo

EXPOSE 8501
# 运行：docker run -p 8501:8501 --env-file .env zhibei
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
