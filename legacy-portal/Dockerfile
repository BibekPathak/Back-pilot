FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8081

ENV PORT=8081
CMD ["python", "-m", "uvicorn", "portal:app", "--host", "0.0.0.0", "--port", "8081"]
