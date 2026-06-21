# Container image for running the briefer as a Cloud Run Job.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . ./

# The job processes the previous court day and emails + archives it.
CMD ["python", "main.py", "--yesterday"]
