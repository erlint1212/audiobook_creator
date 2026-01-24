import os

def generate_project_context(output_file="project_context.txt", ignore_dirs=None):
    """
    Scans the current directory, generates a file tree, and appends the content
    of ONLY .py files into a single output text file.
    """
    
    # Get the name of this script to exclude it from the output
    current_script = os.path.basename(__file__)
    
    # Default directories to ignore (keeps the tree clean)
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'node_modules', 'venv', 'env', '.idea', '.vscode', 'build', 'dist', '.venv'}

    # 1. Generate the File Tree Structure
    # We still list all files in the tree so the AI sees the full structure
    tree_str = "Project Directory Structure:\n"
    tree_str += "============================\n"
    
    for root, dirs, files in os.walk("."):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        level = root.replace(os.path.sep, '/').count('/')
        indent = ' ' * 4 * (level)
        tree_str += "{}{}/\n".format(indent, os.path.basename(root))
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if f != output_file:
                tree_str += "{}{}\n".format(subindent, f)

    tree_str += "\n\n"

    # 2. Read File Contents (STRICTLY .py ONLY)
    content_str = "File Contents:\n"
    content_str += "==============\n"

    for root, dirs, files in os.walk("."):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for file in files:
            # Skip this script itself
            if file == current_script:
                continue
            
            # STRICT FILTER: Skip anything that is NOT a .py file
            if not file.endswith('.py'):
                continue

            file_path = os.path.join(root, file)
            
            content_str += f"\n--- START OF FILE: {file_path} ---\n"
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content_str += f.read()
            except Exception as e:
                content_str += f"[Error reading file: {e}]"
            
            content_str += f"\n--- END OF FILE: {file_path} ---\n"

    # 3. Write everything to the output file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(tree_str)
            f.write(content_str)
        print(f"Success! Context saved to '{output_file}' (Only .py files included)")
    except Exception as e:
        print(f"Error writing output file: {e}")

if __name__ == "__main__":
    generate_project_context()
