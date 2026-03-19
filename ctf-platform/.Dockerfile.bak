# ========================================
# Dockerfile for CTF Platform
# 
# This builds a Docker image that contains your application.
# 
# TO BUILD:
#   docker build -t ctf-platform .
# 
# TO RUN:
#   docker run -p 5000:5000 ctf-platform
# ========================================

# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Install system dependencies
# These are needed for some Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
# Docker caches layers, so if requirements don't change,
# it won't reinstall packages on every build
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for SQLite database with proper permissions
RUN mkdir -p /app/instance && chmod 777 /app/instance

# Expose port 5050
# This is the port the app runs on inside the container
EXPOSE 5050

# Set environment variables
ENV FLASK_APP=run.py
ENV PYTHONUNBUFFERED=1

# Run the application with gunicorn (production server)
# For development, you can use: CMD ["python", "run.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "run:app"]

# ========================================
# NOTES:
# - The app will be accessible at http://localhost:5050
# - Database is stored in /app/instance/ctf.db inside container
# - For persistent data, use Docker volumes (see docker-compose.yml)
# ========================================
