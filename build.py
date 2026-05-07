#!/usr/bin/env python3
"""
Build script for creating the storage health check executable using PyInstaller.
"""

import os
import subprocess
import sys

def build_exe():
    """Build the standalone executable."""
    print("Building storage health check executable...")

    # Ensure we're in the correct directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # PyInstaller command
    cmd = [
        'pyinstaller',
        '--onefile',  # Create single executable
        '--windowed',  # No console window (for Windows)
        '--name', 'storage_health_check',
        'storage_health_check.py'
    ]

    try:
        subprocess.run(cmd, check=True)
        print("Build completed successfully!")
        print("Executable created: dist/storage_health_check.exe")
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print("PyInstaller not found. Please install it with: pip install pyinstaller")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()