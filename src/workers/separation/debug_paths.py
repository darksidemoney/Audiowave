#!/usr/bin/env python3
import os
import sys
from pathlib import Path

print("Current working directory:", os.getcwd())
print("Arguments:", sys.argv)

if len(sys.argv) > 1:
    input_path = sys.argv[1]
    print("Input path:", input_path)
    
    # Check if file exists
    path = Path(input_path)
    print("Path exists:", path.exists())
    print("Path is file:", path.is_file())
    
    # Check absolute path
    abs_path = path.absolute()
    print("Absolute path:", abs_path)
    print("Absolute path exists:", abs_path.exists()) 