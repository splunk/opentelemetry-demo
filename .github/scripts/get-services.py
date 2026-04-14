#!/usr/bin/env python3
"""
Get list of services from services.yaml

Usage:
    get-services.py --manifest       # Returns services with manifest: true and NO group (main manifest)
    get-services.py --manifest-all   # Returns ALL services with manifest: true (regardless of group)
    get-services.py --build          # Returns services with build: true (all groups)
    get-services.py --all            # Returns all services
    get-services.py --group lambda   # Returns services with group: lambda
    get-services.py --group dc-shim  # Returns services with group: dc-shim
    get-services.py --groups         # Returns list of unique group names
"""

import yaml
import sys

def main():
    filter_type = sys.argv[1] if len(sys.argv) > 1 else '--all'
    filter_value = sys.argv[2] if len(sys.argv) > 2 else None

    # Read services.yaml
    with open('services.yaml', 'r') as f:
        config = yaml.safe_load(f)

    services = config.get('services', [])
    result = []

    for svc in services:
        name = svc.get('name')
        if not name:
            continue

        if filter_type == '--manifest':
            # Main manifest only: manifest: true AND no group
            if svc.get('manifest', False) and not svc.get('group'):
                result.append(name)
        elif filter_type == '--manifest-all':
            # All manifest services regardless of group
            if svc.get('manifest', False):
                result.append(name)
        elif filter_type == '--build':
            if svc.get('build', False):
                result.append(name)
        elif filter_type == '--group':
            # Filter by specific group name
            if filter_value and svc.get('group') == filter_value and svc.get('manifest', False):
                result.append(name)
        elif filter_type == '--groups':
            # Collect unique group names
            group = svc.get('group')
            if group and group not in result:
                result.append(group)
        elif filter_type == '--all':
            result.append(name)

    # Output as space-separated list
    print(' '.join(result))
    return 0

if __name__ == '__main__':
    sys.exit(main())
