FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY . .

RUN chown -R app:app /app
USER app

CMD ["sh", "-c", "uvicorn web.main:app --host 0.0.0.0 --port ${PORT}"]
