FROM python:3.6-slim-stretch
RUN pip install boto3
RUN mkdir /ssr
COPY snapshot_restore.py /ssr/snapshot_restore.py
RUN chmod +x /ssr/snapshot_restore.py
CMD [""]
