FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps zcatalyst-sdk==1.4.0

# The embedding model is baked in; the index is not. The model is a fixed
# 90 MB artifact that changes only when we deliberately change models — and
# if it ever does, MIN_RELEVANCE stops being meaningful, so that should be
# an image rebuild. The index changes every time the corpus does, which is
# the agent's routine path, so it comes from Stratus at startup instead.
COPY models ./models
COPY server.py embedder.py retriever.py entity_gate.py index_store.py ./
COPY static ./static

# AppSail supplies the port it wants listened on; 9000 is its default.
ENV X_ZOHO_CATALYST_LISTEN_PORT=9000
EXPOSE 9000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${X_ZOHO_CATALYST_LISTEN_PORT:-9000}"]
