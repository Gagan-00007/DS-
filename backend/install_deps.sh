#!/bin/bash
# Installs backend dependencies in the order that avoids the dlib
# source-build trap (see requirements.txt for the full explanation).
#
# Usage: bash install_deps.sh

set -e

echo "Installing core web/db/auth dependencies..."
pip install fastapi uvicorn[standard] sqlalchemy pydantic \
    python-jose[cryptography] "passlib[bcrypt]" bcrypt==4.0.1 python-multipart

echo "Installing dlib-bin (prebuilt binary, avoids needing CMake/C++ toolchain)..."
pip install dlib-bin

echo "Installing face_recognition WITHOUT its declared deps (skips the dlib source-build trap)..."
pip install --no-deps face_recognition face_recognition_models

echo "Installing face_recognition's real remaining dependencies..."
pip install click Pillow numpy

echo "Installing mediapipe, opencv, and scheduler..."
pip install mediapipe opencv-python apscheduler

echo ""
echo "Verifying..."
python3 -c "import face_recognition; import mediapipe; import cv2; import fastapi; print('All backend dependencies installed correctly.')"
