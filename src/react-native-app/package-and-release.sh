#!/bin/bash

# Script to package iOS and Android builds and create a GitHub release
# Usage: ./package-and-release.sh <version-number>
# Example: ./package-and-release.sh 1.0.0

set -e  # Exit on error

# Check if version number is provided
if [ -z "$1" ]; then
    echo "Error: Version number required"
    echo "Usage: ./package-and-release.sh <version-number>"
    echo "Example: ./package-and-release.sh 1.0.0"
    exit 1
fi

VERSION=$1
PACKAGE_NAME="astronomy-shop-mobile-${VERSION}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

# Create zip file in the project root
ZIP_FILE="${SCRIPT_DIR}/${PACKAGE_NAME}.zip"
echo ""
echo "Creating zip package..."
cd "$TEMP_DIR"
zip -r "$ZIP_FILE" "$PACKAGE_NAME" > /dev/null

# Get zip file size
ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo "✓ Package created: ${PACKAGE_NAME}.zip (${ZIP_SIZE})"

# Clean up temp directory
rm -rf "$TEMP_DIR"
echo "✓ Temporary files cleaned up"

# Create GitHub release
echo ""
echo "Creating GitHub release..."
cd "$SCRIPT_DIR/../.."  # Go to repo root

# Check if gh CLI is available
if ! command -v gh &> /dev/null; then
    echo "Warning: GitHub CLI (gh) not found. Skipping GitHub release."
    echo "You can manually create a release and upload: $ZIP_FILE"
    echo ""
    echo "Package ready at: $ZIP_FILE"
    exit 0
fi

# Check if already logged in to gh
if ! gh auth status &> /dev/null; then
    echo "Warning: Not authenticated with GitHub CLI."
    echo "Run 'gh auth login' to authenticate, then try again."
    echo ""
    echo "Package ready at: $ZIP_FILE"
    exit 0
fi

# Create the release
echo "Creating release v${VERSION}..."
gh release create "mobile-v${VERSION}" \
    "$ZIP_FILE" \
    --title "Mobile App v${VERSION}" \
    --notes "## Mobile App Release v${VERSION}

### Included Builds
- iOS (.ipa) - Release build for real devices
- Android (.apk) - Release APK

### Features
- Splunk RUM instrumentation
- Connected to astronomy-shop backend
- Full telemetry and observability

### Deployment
Ready for Sauce Labs testing or manual deployment.

**Built on:** $(date '+%Y-%m-%d %H:%M:%S')" \
    --repo $(git remote get-url origin | sed 's/.*github.com[:/]\(.*\)\.git/\1/' | sed 's/.*github.com[:/]\(.*\)/\1/')

echo ""
echo "=========================================="
echo "✓ Release created successfully!"
echo "=========================================="
echo "Package: ${PACKAGE_NAME}.zip"
echo "Release: mobile-v${VERSION}"
echo ""
echo "View release: $(git remote get-url origin | sed 's/\.git$//')/releases/tag/mobile-v${VERSION}"
