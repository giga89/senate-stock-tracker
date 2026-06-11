FROM python:3.11-slim

WORKDIR /app

# Install dependencies for building some python packages if needed and cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Setup cron job to run the collector and llm analysis daily at 2 AM
RUN echo "0 2 * * * root cd /app && PYTHONPATH=/app python backend/collector.py >> /var/log/cron.log 2>&1" > /etc/cron.d/senate-cron
RUN echo "30 2 * * * root cd /app && PYTHONPATH=/app python backend/llm_analysis.py >> /var/log/cron.log 2>&1" >> /etc/cron.d/senate-cron
RUN chmod 0644 /etc/cron.d/senate-cron
RUN crontab /etc/cron.d/senate-cron

# Create log file
RUN touch /var/log/cron.log

# Script to start both cron and streamlit
RUN echo '#!/bin/sh\ncron\nPYTHONPATH=/app python backend/collector.py\nPYTHONPATH=/app python backend/llm_analysis.py\nstreamlit run frontend/app.py --server.port=8501 --server.address=0.0.0.0' > /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8501

CMD ["/app/start.sh"]
