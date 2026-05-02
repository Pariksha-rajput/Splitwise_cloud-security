FROM python:3.11-slim

WORKDIR /app

COPY Spiltwise/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Spiltwise/app.py Spiltwise/security.py ./
COPY Spiltwise/templates/ templates/

RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
