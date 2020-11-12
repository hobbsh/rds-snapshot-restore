FROM python:3.7-slim-stretch
WORKDIR /app
COPY app/* ./
RUN chmod -R +x *.py
RUN pip install -r requirements.txt

CMD ["/usr/local/bin/python3", "/app/snapshot_restore.py"]
