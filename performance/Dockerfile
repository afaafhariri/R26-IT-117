FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.3.1+cpu \
    -r requirements.txt
COPY . .
EXPOSE 5004
CMD ["python", "main.py"]
