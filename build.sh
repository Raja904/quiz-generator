#!/usr/bin/env bash
# build.sh - Render Build Script
set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Setting up zero-RAM OCR (Ocrad)..."
if [ ! -f "ocrad_bin" ]; then
    echo "Downloading and compiling ocrad from source..."
    # Download GNU Ocrad source code
    curl -O http://ftp.gnu.org/gnu/ocrad/ocrad-0.28.tar.gz
    tar -xzf ocrad-0.28.tar.gz
    cd ocrad-0.28
    
    # Compile it using the native Ubuntu C++ compiler on Render
    ./configure
    make
    
    # Move the compiled executable to the root directory
    cp ocrad ../ocrad_bin
    cd ..
    
    # Clean up source files to save disk space
    rm -rf ocrad-0.28 ocrad-0.28.tar.gz
    echo "ocrad compiled successfully!"
else
    echo "ocrad_bin already exists, skipping compilation."
fi

echo "==> Build complete!"
