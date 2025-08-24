# Use official Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source code
COPY . .

# Expose port Flask will run on
EXPOSE 5000

# Run Gunicorn server with 4 workers
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]