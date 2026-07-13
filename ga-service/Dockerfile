FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The GA runs once to completion then exits (it is a batch job, not a server)
CMD ["python", "-u", "main.py"]
