#!/bin/bash

# Script to build iOS and Android packages for Sauce Labs
# Usage: ./build-saucelabs.sh <version>
# Example: ./build-saucelabs.sh 1.2.3

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Validate version number format
validate_version() {
    local version=$1
    # Allow formats like: 1, 1.1, 1.1.1, 1.1.1.1, 1.1.1.1.1 up to 99.999.999
    if [[ ! $version =~ ^[0-9]{1,2}(\.[0-9]{1,3}){0,4}$ ]]; then
        print_error "Invalid version format: $version"
        echo "Version must be in format: x.xx.xxx (e.g., 1, 1.2, 1.2.3, 1.2.3.4, etc.)"
        echo "Maximum: 99.999.999.999.999"
        exit 1
    fi
}

# Check if version number is provided
if [ -z "$1" ]; then
    print_error "Version number required"
    echo "Usage: ./build-saucelabs.sh <version-number>"
    echo "Example: ./build-saucelabs.sh 1.2.3"
    exit 1
fi

VERSION=$1
validate_version "$VERSION"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

echo "=========================================="
echo "Building Sauce Labs Package v${VERSION}"
echo "=========================================="

# Step 1: Update .env file with new version
echo ""
echo "Step 1: Updating .env file with version ${VERSION}..."
if [ ! -f "$ENV_FILE" ]; then
    print_error ".env file not found at: $ENV_FILE"
    exit 1
fi

# Backup original .env
cp "$ENV_FILE" "${ENV_FILE}.backup"
print_info "Backed up .env file"

# Update or add EXPO_PUBLIC_APP_VERSION
if grep -q "^EXPO_PUBLIC_APP_VERSION=" "$ENV_FILE"; then
    # Version line exists, update it (macOS compatible)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^EXPO_PUBLIC_APP_VERSION=.*/EXPO_PUBLIC_APP_VERSION=${VERSION}/" "$ENV_FILE"
    else
        sed -i "s/^EXPO_PUBLIC_APP_VERSION=.*/EXPO_PUBLIC_APP_VERSION=${VERSION}/" "$ENV_FILE"
    fi
    print_info "Updated EXPO_PUBLIC_APP_VERSION=${VERSION} in .env"
else
    # Version line doesn't exist, add it
    echo "EXPO_PUBLIC_APP_VERSION=${VERSION}" >> "$ENV_FILE"
    print_info "Added EXPO_PUBLIC_APP_VERSION=${VERSION} to .env"
fi

# Step 2: Clean previous builds
echo ""
echo "Step 2: Cleaning previous builds..."
rm -rf "${SCRIPT_DIR}/ios/build"
rm -rf "${SCRIPT_DIR}/saucelabs-package"
rm -f "${SCRIPT_DIR}"/astronomy-shop-saucelabs-v*.zip
print_info "Cleaned previous builds"

# Step 3: Build iOS device version
echo ""
echo "Step 3: Building iOS device version..."
echo "This may take several minutes..."
cd "$SCRIPT_DIR"

xcodebuild -workspace ios/reactnativeapp.xcworkspace \
    -scheme reactnativeapp \
    -configuration Release \
    -sdk iphoneos \
    -derivedDataPath ios/build \
    CODE_SIGN_IDENTITY="" \
    CODE_SIGNING_REQUIRED=NO \
    CODE_SIGNING_ALLOWED=NO \
    > /dev/null 2>&1

if [ $? -eq 0 ]; then
    print_info "iOS build completed"
else
    print_error "iOS build failed"
    print_warning "Restoring original .env..."
    mv "${ENV_FILE}.backup" "$ENV_FILE"
    exit 1
fi

# Step 4: Build Android APK
echo ""
echo "Step 4: Building Android release APK..."
echo "This may take several minutes..."

cd "${SCRIPT_DIR}/android"
./gradlew clean > /dev/null 2>&1
./gradlew assembleRelease > /dev/null 2>&1

cd "$SCRIPT_DIR"

if [ $? -eq 0 ]; then
    print_info "Android build completed"
else
    print_error "Android build failed"
    print_warning "Restoring original .env..."
    mv "${ENV_FILE}.backup" "$ENV_FILE"
    exit 1
fi

# Step 5: Verify builds exist
echo ""
echo "Step 5: Verifying build artifacts..."

IOS_APP="${SCRIPT_DIR}/ios/build/Build/Products/Release-iphoneos/reactnativeapp.app"
ANDROID_APK="${SCRIPT_DIR}/android/app/build/outputs/apk/release/app-release.apk"

if [ ! -d "$IOS_APP" ]; then
    print_error "iOS .app file not found at: $IOS_APP"
    print_warning "Restoring original .env..."
    mv "${ENV_FILE}.backup" "$ENV_FILE"
    exit 1
fi

if [ ! -f "$ANDROID_APK" ]; then
    print_error "Android .apk file not found at: $ANDROID_APK"
    print_warning "Restoring original .env..."
    mv "${ENV_FILE}.backup" "$ENV_FILE"
    exit 1
fi

print_info "iOS build found: reactnativeapp.app"
print_info "Android build found: app-release.apk"

# Step 6: Create package structure
echo ""
echo "Step 6: Creating Sauce Labs package structure..."

mkdir -p "${SCRIPT_DIR}/saucelabs-package/ios"
mkdir -p "${SCRIPT_DIR}/saucelabs-package/android"

# Zip iOS app
cd "${SCRIPT_DIR}/ios/build/Build/Products/Release-iphoneos"
zip -r "${SCRIPT_DIR}/saucelabs-package/ios/astronomy-shop-ios.zip" reactnativeapp.app > /dev/null 2>&1
cd "$SCRIPT_DIR"
print_info "Created iOS zip package"

# Copy Android APK
cp "$ANDROID_APK" "${SCRIPT_DIR}/saucelabs-package/android/astronomy-shop.apk"
print_info "Copied Android APK"

# Step 7: Create final zip package
echo ""
echo "Step 7: Creating final Sauce Labs package..."

PACKAGE_NAME="astronomy-shop-saucelabs-v${VERSION}.zip"

cd "$SCRIPT_DIR"
zip -r "${PACKAGE_NAME}" saucelabs-package/ > /dev/null 2>&1

# Get file sizes
FINAL_ZIP_SIZE=$(du -h "${SCRIPT_DIR}/${PACKAGE_NAME}" | cut -f1)
IOS_ZIP_SIZE=$(du -h "${SCRIPT_DIR}/saucelabs-package/ios/astronomy-shop-ios.zip" | cut -f1)
ANDROID_APK_SIZE=$(du -h "${SCRIPT_DIR}/saucelabs-package/android/astronomy-shop.apk" | cut -f1)

print_info "Created final package: ${PACKAGE_NAME} (${FINAL_ZIP_SIZE})"

# Clean up backup
rm -f "${ENV_FILE}.backup"

echo ""
echo "=========================================="
echo "✓ Build completed successfully!"
echo "=========================================="
echo "Version: ${VERSION}"
echo ""
echo "Package contents:"
echo "  └─ saucelabs-package/"
echo "      ├─ ios/"
echo "      │   └─ astronomy-shop-ios.zip (${IOS_ZIP_SIZE})"
echo "      └─ android/"
echo "          └─ astronomy-shop.apk (${ANDROID_APK_SIZE})"
echo ""
echo "Final package: ${PACKAGE_NAME} (${FINAL_ZIP_SIZE})"
echo "Location: ${SCRIPT_DIR}/${PACKAGE_NAME}"
echo ""
echo "Changes made:"
echo "  ✓ Updated .env with EXPO_PUBLIC_APP_VERSION=${VERSION}"
echo "  ✓ Built iOS device version (ARM64)"
echo "  ✓ Built Android release APK"
echo "  ✓ Created Sauce Labs package"
echo ""
echo "Upload to Sauce Labs:"
echo "  - Extract the zip and upload individual files, or"
echo "  - Upload ${PACKAGE_NAME} directly"
echo ""
