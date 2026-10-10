# SageMaker inference container (BYOC) for SolarRooftop roof segmentation. CPU-only (Serverless Inference).
# Build from the repo root for x86_64 (SageMaker Serverless runs on x86):
#   docker build --platform linux/amd64 -f ml/serve/Dockerfile -t solarrooftop-seg:v1 .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_DIR=/opt/ml/model \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY ml/serve/requirements-serve.txt /opt/program/requirements-serve.txt
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /opt/program/requirements-serve.txt

COPY ml/serve/segment.py ml/serve/serve.py /opt/program/
WORKDIR /opt/program
EXPOSE 8080

# SageMaker runs `docker run <image> serve`
ENTRYPOINT ["python", "/opt/program/serve.py"]
