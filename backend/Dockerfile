# Example of what a standard Computer Vision Dockerfile looks like
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies required by OpenCV and MediaPipe
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0

# Copy your requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app's code
COPY . .

# Run the app (this command might differ based on your tutorial)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
