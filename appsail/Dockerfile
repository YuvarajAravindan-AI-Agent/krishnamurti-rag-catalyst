# Built from the REPOSITORY ROOT, not from appsail/:
#
#   podman build --platform linux/amd64 -f appsail/Dockerfile -t localhost/krishnamurti-rag:latest .
#
# appsail/models is a symlink to ../models for local development, and a
# build context rooted at appsail/ cannot follow it out of the context.
# Rooting the context at the repo means the image builds from a clean
# clone with no pre-staging step — see .containerignore for what is kept
# out, which is most of the repo by size.
FROM python:3.12-slim
WORKDIR /app

COPY appsail/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps zcatalyst-sdk==1.4.0

# The embedding model is baked in; the index is not. The model is a fixed
# 90 MB artifact that changes only when we deliberately change models — and
# if it ever does, MIN_RELEVANCE stops being meaningful, so that should be
# an image rebuild. The index changes every time the corpus does, which is
# the agent's routine path, so it comes from Stratus at startup instead.
COPY models ./models
COPY appsail/server.py appsail/embedder.py appsail/retriever.py \
     appsail/entity_gate.py appsail/index_store.py ./
COPY appsail/static ./static

# AppSail supplies the port it wants listened on; 9000 is its default.
ENV X_ZOHO_CATALYST_LISTEN_PORT=9000
EXPOSE 9000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${X_ZOHO_CATALYST_LISTEN_PORT:-9000}"]
