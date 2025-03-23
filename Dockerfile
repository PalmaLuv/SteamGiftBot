FROM python:3.11

WORKDIR /
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.python
CMD ["python", "main.py"]