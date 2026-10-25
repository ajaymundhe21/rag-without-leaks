FROM python:3.12-slim
# wordllama has no ready wheel for Linux on ARM (Apple Silicon), so pip builds it and needs a compiler.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
# Long timeout and retries for slow networks.
# wordllama looks for its tokenizer under "tokenizer/" but ships it as "tokenizers/", so we link it.
RUN pip install --no-cache-dir --default-timeout=300 --retries 10 -r requirements.txt \
    && python -c "import os, wordllama; d = os.path.dirname(wordllama.__file__); t = os.path.join(d, 'tokenizer'); os.path.exists(t) or os.symlink('tokenizers', t)"
COPY . .
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
