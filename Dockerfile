FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements/ requirements/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements/production.txt && \
    rm -rf requirements

# Copy application code
COPY . .

# Run the bot
CMD ["python", "bot.py"]
