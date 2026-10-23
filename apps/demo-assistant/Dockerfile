FROM python:3.12-slim
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "pydantic>=2.7" && useradd -r -u 10001 demo
COPY app.py /app/app.py
WORKDIR /app
USER demo
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
