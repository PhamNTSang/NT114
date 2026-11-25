FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt
COPY selfheal ./selfheal
COPY models/current.zip ./models/current.zip
COPY models/forecaster ./models/forecaster
RUN useradd --create-home --shell /usr/sbin/nologin appuser && mkdir -p data && chown -R appuser /app
USER appuser
ENTRYPOINT ["python", "-m"]
CMD ["selfheal.controller"]