FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY copilot/ ./copilot/
COPY main.py .
COPY conftest.py .
COPY .env.example .

# Create data directory for LTM persistence
RUN mkdir -p data

# Default command
CMD ["python", "main.py"]