FROM python:3.7-slim-stretch
WORKDIR /app
COPY app/requirements.txt ./
RUN pip install -r requirements.txt
COPY app/* ./
RUN chmod -R +x *.py

CMD ["/usr/local/bin/python3", "/app/snapshot_restore.py"]
