# 1. Use the official Python 3.10 slim image
FROM python:3.10-slim

# 2. Set the working directory inside the server
WORKDIR /app

# 3. Install system dependencies for OpenCV, MediaPipe, and dlib
# (Includes the libgl1 fix and the cmake/build-essential fix)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. Copy the requirements file into the server
COPY requirements.txt .

# 5. THE MAGIC FIX: Force the C++ compiler to use only 1 core
# This stops Render from running out of RAM and crashing!
ENV CMAKE_BUILD_PARALLEL_LEVEL=1

# 6. Install the Python packages
RUN pip install --no-cache-dir -r requirements.txt

# 7. Copy all of your Python scripts (main.py, etc.) into the server
COPY . .

# 8. Start the server AND seed the database first!
# The "sh -c" lets us string two commands together with &&
CMD ["sh", "-c", "python seed.py && uvicorn main:app --host 0.0.0.0 --port 10000"]
