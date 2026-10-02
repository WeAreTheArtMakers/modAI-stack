FROM python:3.11-slim
WORKDIR /app
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
COPY requirements-runtime.txt .
# Containers are CPU-first by default; GPU-specific serving remains an explicit deployment choice.
RUN pip install --no-cache-dir --index-url ${PYTORCH_INDEX_URL} "torch>=2.4" \
    && pip install --no-cache-dir -r requirements-runtime.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
