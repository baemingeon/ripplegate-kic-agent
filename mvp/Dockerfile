FROM python:3.11-slim

WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV KIC_HOST=0.0.0.0
ENV PORT=8766
ENV KIC_LLM_POLICY=disabled

EXPOSE 8766
CMD ["sh", "-c", "python ripplegate_server.py --host ${KIC_HOST} --port ${PORT:-8766}"]
