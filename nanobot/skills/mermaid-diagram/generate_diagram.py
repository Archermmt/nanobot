#!/usr/bin/env python3
"""
Mermaid Diagram Generator Script

This script helps generate and render Mermaid diagrams to images.
Usage:
    python -m mermaid_diagram generate "diagram_code" output_path.png
"""
import os
import sys
import subprocess
from pathlib import Path


MEDIA_FOLDER = Path.home() / ".nanobot/media"
DIAGRAMS_DIR = MEDIA_FOLDER / "diagrams"


def ensure_directories():
    """Ensure the diagrams directory exists."""
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Diagrams directory: {DIAGRAMS_DIR}")


def run_mmdc(input_file: str, output_format: str = "png", width: int = 800):
    """
    Run mmdc command to render a mermaid diagram.
    
    Args:
        input_file: Path to .mmd file with mermaid code
        output_format: Output format (png, svg, pdf)
        width: Width of the output image
    """
    # Get base name without extension
    base_name = Path(input_file).stem
    
    # Set default output path
    if output_format == "svg":
        output_ext = "svg"
    elif output_format == "pdf":
        output_ext = "pdf"
    else:
        output_ext = "png"
    
    output_file = str(DIAGRAMS_DIR / f"{base_name}.{output_ext}")
    
    # Build and run mmdc command
    cmd = ["mmdc", "-i", input_file, "-o", output_file, "-w", str(width), "-b", "transparent"]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error rendering diagram: {result.stderr}")
            return None
            
        return output_file
        
    except FileNotFoundError:
        print("Error: 'mmdc' command not found. Please install @mermaid-js/mermaid-cli globally.")
        print("Run: npm install -g @mermaid-js/mermaid-cli")
        return None


def create_test_diagram():
    """Create a test flowchart to verify installation."""
    test_dir = Path(__file__).parent
    mmd_file = test_dir / "test.mmd"
    
    # Create a simple test diagram
    mermaid_code = """flowchart LR
    A[Start] --> B{Is it working?}
    B -->|Yes| C[Great!]
    B -->|No| D[Debug]
    D --> B
    style A fill:#f9f,stroke:#3356d7
    style B fill:#ffe,stroke:#333
    style C fill:#9ae112,stroke:#333
    style D fill:#f4d30a,stroke:#333
"""
    mmd_file.write_text(mermaid_code)
    print(f"Created test diagram at: {mmd_file}")
    return str(mmd_file)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "setup":
        # Setup mode: create directories and show info
        ensure_directories()
        print(f"✓ Ensured directories exist")
        print(f"  - Media folder: {MEDIA_FOLDER}")
        print(f"  - Diagrams will be saved to: {DIAGRAMS_DIR}")
        
        # Check if mmdc is installed
        result = subprocess.run(["which", "mmdc"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ mmdc is installed at: {result.stdout.strip()}")
        else:
            print("✗ mmdc is not installed. Install with: npm install -g @mermaid-js/mermaid-cli")
            
    elif command == "test":
        # Test mode: create and render a simple diagram
        ensure_directories()
        
        mmd_file = create_test_diagram()
        output = run_mmdc(mmd_file)
        
        if output:
            print(f"✓ Successfully rendered test diagram to: {output}")
            
            # Cleanup test file
            os.remove(mmd_file)
        else:
            print("✗ Failed to render test diagram")
            sys.exit(1)
            
    elif command == "render":
        # Render mode: render a specific .mmd file
        if len(sys.argv) < 3:
            print("Usage: python -m mermaid_diagram render <input.mmd>")
            sys.exit(1)
        
        input_file = sys.argv[2]
        if not Path(input_file).exists():
            print(f"Error: File not found: {input_file}")
            sys.exit(1)
            
        ensure_directories()
        output = run_mmdc(input_file)
        
        if output:
            print(f"✓ Successfully rendered to: {output}")
        else:
            print("✗ Failed to render diagram")
            sys.exit(1)
            
    else:
        print(f"Unknown command: {command}")
        print("Available commands: setup, test, render")
        sys.exit(1)