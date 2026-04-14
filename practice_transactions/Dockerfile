FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
COPY requirements/ ./requirements/
RUN pip install --no-cache-dir --no-index --find-links=./requirements -r requirements.txt

COPY . .

ENV DB_TYPE=sqlite

CMD ["python", "main.py"]
