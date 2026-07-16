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

try:
    import yaml
except ImportError:
    yaml = None


def _patch_file(manifest_path, new_image, image_name=None):
    """Rewrite image line(s) in a single manifest file.

    If image_name is given, only replace lines whose image path ends with
    that exact name (before the tag). Prevents clobbering sibling deployments
    when multiple services share a single manifest file
    (e.g. secureapp-loadgen-{java,node,python}).
    """
    if not os.path.exists(manifest_path):
        print(f"Warning: Manifest not found: {manifest_path}")
        return False

    with open(manifest_path, 'r') as f:
        content = f.read()

    if image_name:
        # Match image path ending in /<image_name>:<tag>; keep the leading
        # `  image: ghcr.io/<org>/` prefix, replace whole line with new_image.
        pattern = rf'(\s+image:\s+)ghcr\.io/[^\s:]+/{re.escape(image_name)}:\S+'
    else:
        # Legacy behavior: match any ghcr.io image (per-svc dedicated manifest).
        pattern = r'(\s+image:\s+)ghcr\.io/[^\s]+:\S+'
    updated_content, count = re.subn(pattern, rf'\1{new_image}', content)

    if count > 0:
        with open(manifest_path, 'w') as f:
            f.write(updated_content)
        print(f"✅ Updated {manifest_path} ({count} image line{'s' if count != 1 else ''})")
        print(f"   New image: {new_image}")
        return True

    print(f"⚠️  No image line found in {manifest_path} matching {image_name or 'ghcr.io/*'}")
    return False


def _lookup_manifest_file(service):
    """Read services.yaml for optional manifest_file override."""
    if yaml is None:
        return None
    try:
        with open('services.yaml') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        return None
    for svc in config.get('services', []):
        if svc.get('name') == service:
            return svc.get('manifest_file')
    return None


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
        results = [_patch_file(p, new_image, image_name=image_name) for p in targets]
        return any(results)

    # Scope every sedge by image_name so sibling images in the same
    # manifest (main container + sidecar containers) are not clobbered.
    # Applies to both the manifest_file override case (shared file, e.g.
    # sidecar in target's own manifest) AND the default per-svc path.
    override = _lookup_manifest_file(service)
    target = override or f"src/{service}/{service}-k8s.yaml"
    return _patch_file(target, new_image, image_name=image_name)

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
