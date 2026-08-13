FROM public.ecr.aws/lambda/python:3.12

COPY aws/lambda/requirements.txt /var/task/requirements.txt
RUN pip install --no-cache-dir -r /var/task/requirements.txt

COPY networksecurity/ /var/task/networksecurity/
COPY aws/lambda/handler.py /var/task/handler.py

ENV PHISHGUARD_MODEL_CACHE_DIR=/tmp/phishguard-models
ENV PYTHONUNBUFFERED=1

CMD ["handler.lambda_handler"]
