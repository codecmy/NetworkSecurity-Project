FROM python:3.10-slim

WORKDIR /app
COPY . /app
RUN apt-get update -y && apt-get install -y awscli && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt
CMD [ "python3","app.py" ]