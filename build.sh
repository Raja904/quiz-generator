#!/usr/bin/env bash
# build.sh - Render Build Script
set -e

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Setting up zero-RAM OCR (Ocrad)..."
if [ ! -f "ocrad_bin" ]; then
    echo "Downloading ocrad binary package..."

    URLS=(
        "https://mirrors.kernel.org/ubuntu/pool/universe/o/ocrad/ocrad_0.27-2build1_amd64.deb"
        "http://ftp.osuosl.org/pub/ubuntu/pool/universe/o/ocrad/ocrad_0.27-2build1_amd64.deb"
        "http://archive.ubuntu.com/ubuntu/pool/universe/o/ocrad/ocrad_0.27-2build1_amd64.deb"
    )

    DOWNLOADED=false
    for url in "${URLS[@]}"; do
        echo "Attempting download from: $url"
        if curl -fsSL --connect-timeout 15 --max-time 60 --retry 3 --retry-delay 2 "$url" -o ocrad_0.27-2build1_amd64.deb; then
            DOWNLOADED=true
            echo "Successfully downloaded ocrad package."
            break
        fi
        echo "Failed to download from $url, trying next mirror..."
    done

    if [ "$DOWNLOADED" = true ]; then
        if command -v ar >/dev/null 2>&1; then
            ar x ocrad_0.27-2build1_amd64.deb
            tar -xf data.tar.xz
            cp usr/bin/ocrad ./ocrad_bin
            chmod +x ./ocrad_bin
            rm -rf usr etc data.tar.xz control.tar.xz debian-binary ocrad_0.27-2build1_amd64.deb
            echo "ocrad binary extracted and ready!"
        else
            echo "Warning: 'ar' utility not available. Skipping extraction."
            rm -f ocrad_0.27-2build1_amd64.deb
        fi
    else
        echo "Warning: Could not download ocrad binary from mirrors. App will run with native text extraction (OCR degrades gracefully)."
    fi
else
    echo "ocrad_bin already exists, skipping download."
fi

echo "==> Build complete!"
