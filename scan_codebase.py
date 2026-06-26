import os

# Blacklist extensions
blacklist_ext = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.tiff', '.webp', '.psd', '.ai', '.eps', '.indd', '.raw', '.cr2', '.nef', '.orf', '.sr2', '.arw', '.raf', '.dng', '.rw2',
    '.mp4', '.m4v', '.mov', '.wmv', '.avi', '.avchd', '.flv', '.f4v', '.swf', '.mkv', '.webm', '.mpeg', '.mpg', '.mpe', '.ogg', '.ogv', '.mxf', '.ts', '.m3u8', '.m3u',
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.oga', '.m4a', '.wma', '.aiff', '.alac', '.aif', '.aifc',
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.lzma', '.cab', '.iso', '.dmg', '.toast', '.vcd', '.bin', '.cue',
    '.exe', '.dll', '.so', '.dylib', '.app', '.bat', '.cmd', '.com', '.pif', '.application', '.gadget', '.msi', '.msp', '.mst', '.tmp', '.temp', '.old', '.backup',
    '.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.odg', '.odf', '.sxw', '.stw', '.sxg', '.stw', '.sxi', '.sti', '.sxm', '.stw', '.sxc', '.stc', '.sxw', '.stw', '.sxg', '.stw', '.sxi', '.sti', '.sxm', '.stw', '.sxc', '.stc',
    '.ttf', '.otf', '.woff', '.woff2', '.eot', '.pfb', '.pfm', '.afm', '.bdf', '.pcf', '.snf', '.pfa', '.pfb', '.pfm', '.afm', '.bdf', '.pcf', '.snf',
    '.db', '.sqlite', '.sqlite3', '.sqlitedb', '.mdb', '.accdb', '.odb', '.frm', '.myd', '.myi', '.ibd', '.ibd', '.frm', '.myd', '.myi', '.ibd'
}

def is_binary_file(filepath):
    """Check if file is binary by extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in blacklist_ext

def should_skip_dir(dirname):
    """Check if directory should be skipped."""
    return dirname in ('.git', '__pycache__', '.ipynb_checkpoints')

def main():
    root_dir = os.getcwd()
    total_files = 0
    total_lines = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Modify dirnames in-place to skip unwanted directories
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if is_binary_file(filepath):
                continue

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    # Read the entire file content
                    content = f.read()
                    lines = content.splitlines()
                    num_lines = len(lines)
                    total_files += 1
                    total_lines += num_lines

                    # Optionally, print the file path and first few lines for logging
                    # print(f"File: {filepath} ({num_lines} lines)")
                    # for i, line in enumerate(lines[:3]):
                    #     print(f"  {i+1}: {line}")
            except UnicodeDecodeError:
                # Skip files that are not UTF-8 text (binary despite extension)
                continue
            except Exception as e:
                print(f"Error reading {filepath}: {e}")

    print(f"Total files read: {total_files}")
    print(f"Total lines: {total_lines}")

if __name__ == '__main__':
    main()