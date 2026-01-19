#!/bin/bash

# Script to package iOS and Android builds and commit to releases directory
# Usage: ./package-mobile.sh <version-number>
# Example: ./package-mobile.sh 1.0.0

set -e  # Exit on error

# Check if version number is provided
if [ -z "$1" ]; then
    echo "Error: Version number required"
    echo "Usage: ./package-mobile.sh <version-number>"
    echo "Example: ./package-mobile.sh 1.0.0"
    exit 1
fi

VERSION=$1
PACKAGE_NAME="astronomy-shop-mobile-${VERSION}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RELEASES_DIR="$REPO_ROOT/releases/mobile"

# File paths
IOS_IPA="${SCRIPT_DIR}/ios/build/Build/Products/Release-iphoneos/reactnativeapp.ipa"
ANDROID_APK="${SCRIPT_DIR}/android/app/build/outputs/apk/release/app-release.apk"

echo "=========================================="
echo "Packaging React Native App v${VERSION}"
echo "=========================================="

# Verify files exist
echo "Checking build files..."
if [ ! -f "$IOS_IPA" ]; then
    echo "Error: iOS .ipa file not found at: $IOS_IPA"
    exit 1
fi

if [ ! -f "$ANDROID_APK" ]; then
    echo "Error: Android .apk file not found at: $ANDROID_APK"
    exit 1
fi

echo "✓ iOS build found: $(basename $IOS_IPA)"
echo "✓ Android build found: $(basename $ANDROID_APK)"

# Create temporary directory
TEMP_DIR=$(mktemp -d)
echo ""
echo "Creating package structure in: $TEMP_DIR"

# Create ios and android subdirectories
mkdir -p "$TEMP_DIR/$PACKAGE_NAME/ios"
mkdir -p "$TEMP_DIR/$PACKAGE_NAME/android"

# Copy files
echo "Copying build artifacts..."
cp "$IOS_IPA" "$TEMP_DIR/$PACKAGE_NAME/ios/astronomy-shop.ipa"
cp "$ANDROID_APK" "$TEMP_DIR/$PACKAGE_NAME/android/astronomy-shop.apk"

# Create README for the package
cat > "$TEMP_DIR/$PACKAGE_NAME/README.md" << EOF
# Astronomy Shop Mobile v${VERSION}

Built on: $(date)

## Contents

### iOS
- \`ios/astronomy-shop.ipa\` - iOS app for real devices (ARM64)
- Configuration: Release
- SDK: iphoneos26.0

### Android
- \`android/astronomy-shop.apk\` - Android APK
- Configuration: Release
- Target SDK: Android 34

## Features
- Splunk RUM instrumentation (@splunk/otel-react-native)
- Backend: https://astronomy-shop-us.splunko11y.com
- Full telemetry and observability

## Deployment

### Sauce Labs
Both builds are ready for direct upload to Sauce Labs:
- Upload the .ipa file for iOS device testing
- Upload the .apk file for Android device testing

### Manual Installation

#### iOS
The .ipa file requires proper code signing for installation on physical devices.

#### Android
The .apk can be installed directly:
\`\`\`bash
adb install android/astronomy-shop.apk
\`\`\`

## Build Info
- React Native: 0.74.2
- Expo: 51.0.39
- Splunk RUM: 0.3.4
EOF

echo "✓ README created"

# Create releases directory in repo if it doesn't exist
echo ""
echo "Setting up releases directory..."
mkdir -p "$RELEASES_DIR"

# Create zip file in releases directory
ZIP_FILE="${RELEASES_DIR}/${PACKAGE_NAME}.zip"
echo "Creating zip package..."
cd "$TEMP_DIR"
zip -r "$ZIP_FILE" "$PACKAGE_NAME" > /dev/null

# Get zip file size
ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "✓ Package created: ${PACKAGE_NAME}.zip (${ZIP_SIZE})"

# Clean up temp directory
rm -rf "$TEMP_DIR"
echo "✓ Temporary files cleaned up"

# Create or update index file
echo ""
echo "Updating releases index..."
INDEX_FILE="${RELEASES_DIR}/README.md"

# Create header if file doesn't exist
if [ ! -f "$INDEX_FILE" ]; then
    cat > "$INDEX_FILE" << 'EOF'
# Mobile App Releases

This directory contains packaged mobile app builds for iOS and Android.

## Available Versions

EOF
fi

# Add this version to the index if not already there
if ! grep -q "### Version ${VERSION}" "$INDEX_FILE"; then
    cat >> "$INDEX_FILE" << EOF

### Version ${VERSION}
- **File**: [\`${PACKAGE_NAME}.zip\`](./${PACKAGE_NAME}.zip)
- **Built**: $(date '+%Y-%m-%d %H:%M:%S')
- **Size**: ${ZIP_SIZE}
- **Contents**: iOS .ipa + Android .apk

EOF
    echo "✓ Added to releases index"
else
    echo "✓ Version already in index"
fi

# Git operations
echo ""
echo "Committing to repository..."
cd "$REPO_ROOT"

# Check if there are changes to commit (including untracked files)
if [ -z "$(git status --porcelain releases/)" ]; then
    echo "✓ No changes to commit (release already exists)"
else
    git add releases/mobile/
    git commit -m "Release mobile app v${VERSION}

- iOS build (iphoneos26.0)
- Android build (API 34)
- Includes Splunk RUM instrumentation"

    echo "✓ Changes committed"

    # Ask if user wants to push
    echo ""
    read -p "Push changes to origin? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        CURRENT_BRANCH=$(git branch --show-current)
        git push origin "$CURRENT_BRANCH"
        echo "✓ Pushed to origin/$CURRENT_BRANCH"
    else
        echo "⚠ Changes committed locally but not pushed"
        echo "  Run 'git push' when ready to publish"
    fi
fi

echo ""
echo "=========================================="
echo "✓ Package created successfully!"
echo "=========================================="
echo "Location: releases/mobile/${PACKAGE_NAME}.zip"
echo "Size: ${ZIP_SIZE}"
echo ""
echo "To download:"
echo "  git clone <repo>"
echo "  cd releases/mobile"
echo "  unzip ${PACKAGE_NAME}.zip"
