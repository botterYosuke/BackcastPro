FROM python:3.11-slim
ENV PYTHONUNBUFFERED=True
ENV PYTHONPATH=/app/src
WORKDIR /app

COPY cloud-job/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/BackcastPro/ /app/src/BackcastPro/
COPY src/trading_data/ /app/src/trading_data/
COPY cloud-job/update_stocks_price.py /app/update_stocks_price.py

CMD ["python", "/app/update_stocks_price.py"]
