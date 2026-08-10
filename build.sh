#!/usr/bin/env bash
# build.sh - Render Build Script
set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Setting up zero-RAM OCR (Ocrad)..."
if [ ! -f "ocrad_bin" ]; then
    echo "Downloading and compiling ocrad from source..."
    # Download the pre-compiled Ocrad binary directly from Ubuntu archives
    # Ubuntu 22.04 (Jammy) uses version 0.27-2build1
    curl -LO http://archive.ubuntu.com/ubuntu/pool/universe/o/ocrad/ocrad_0.27-2build1_amd64.deb
    
    # Extract the .deb package (it's an 'ar' archive containing data.tar.xz)
    ar x ocrad_0.27-2build1_amd64.deb
    tar -xf data.tar.xz
    
    # Move the compiled executable to the root directory
    cp usr/bin/ocrad ./ocrad_bin
    chmod +x ./ocrad_bin
    
    # Clean up extraction folders
    rm -rf usr etc data.tar.xz control.tar.xz debian-binary ocrad_0.27-2build1_amd64.deb
    echo "ocrad binary downloaded and extracted successfully!"
else
    echo "ocrad_bin already exists, skipping compilation."
fi

echo "==> Build complete!"
