#!/usr/bin/env python3
"""
Update source k8s manifest files with newly built image references.
This ensures manifests always reference the last successfully built images.

Usage: python3 update-manifest-images.py <service> <registry> <image_name> <version>
Example: python3 update-manifest-images.py llm ghcr.io/hagen-p/opentelemetry-demo-splunk otel-llm fixing-bug-1
"""

import sys
import re
import os

def _patch_file(manifest_path, new_image):
    """Rewrite the image line in a single manifest file."""
    if not os.path.exists(manifest_path):
        print(f"Warning: Manifest not found: {manifest_path}")
        return False

    with open(manifest_path, 'r') as f:
        content = f.read()

    # Matches: image: ghcr.io/*/anything:any-tag
    pattern = r'(\s+image:\s+)ghcr\.io/[^\s]+:\S+'
    updated_content, count = re.subn(pattern, rf'\1{new_image}', content)

    if count > 0:
        with open(manifest_path, 'w') as f:
            f.write(updated_content)
        print(f"✅ Updated {manifest_path}")
        print(f"   New image: {new_image}")
        return True

    print(f"⚠️  No image line found in {manifest_path}")
    return False


def update_manifest_image(service, registry, image_name, version):
    """Update the image line in a service's k8s manifest(s)."""
    new_image = f"{registry}/{image_name}:{version}"

    # Payment ships as A/B variants; stitch reads payment-vA / payment-vB.
    # Keep payment-k8s.yaml in sync too (legacy fallback path).
    if service == 'payment':
        targets = [
            f"src/{service}/payment-vA-k8s.yaml",
            f"src/{service}/payment-vB-k8s.yaml",
            f"src/{service}/{service}-k8s.yaml",
        ]
        results = [_patch_file(p, new_image) for p in targets]
        return any(results)

    return _patch_file(f"src/{service}/{service}-k8s.yaml", new_image)

def main():
    if len(sys.argv) != 5:
        print("Usage: update-manifest-images.py <service> <registry> <image_name> <version>")
        print("Example: update-manifest-images.py llm ghcr.io/hagen-p/opentelemetry-demo-splunk otel-llm fixing-bug-1")
        sys.exit(1)

    service = sys.argv[1]
    registry = sys.argv[2]
    image_name = sys.argv[3]
    version = sys.argv[4]

    print(f"Updating manifest for {service}...")
    success = update_manifest_image(service, registry, image_name, version)

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
