FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app

# Install Python deps for the API
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
