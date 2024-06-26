#!/usr/bin/env python
# -*- coding: utf8 -*-

import subprocess
import os

def windows_to_wsl_path(windows_path):
    # Use wslpath to convert Windows path to WSL path
    result = subprocess.run(['wslpath', windows_path], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Error converting path: {result.stderr.strip()}")
    return result.stdout.strip()

def rename_file_windows_path(old_windows_path, new_windows_path):
    # Convert the Windows paths to WSL paths
    old_wsl_path = windows_to_wsl_path(old_windows_path)
    new_wsl_path = windows_to_wsl_path(new_windows_path)
    
    print(f"Renaming via WSL: {old_wsl_path} to {new_wsl_path}")
    # Rename the file
    os.rename(old_wsl_path, new_wsl_path)

# Example usage
old_windows_path = r'T:\Temp\Goofy Windows\My Sub Folder\New Text Document.txt'
new_windows_path = r'T:\Temp\Goofy Windows\My Sub Folder\Renamed Text Document.txt'

try:
    rename_file_windows_path(old_windows_path, new_windows_path)
    print(f"File renamed successfully from {old_windows_path} to {new_windows_path}")
except Exception as e:
    print(f"Error: {e}")

