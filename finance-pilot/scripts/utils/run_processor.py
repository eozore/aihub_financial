import sys
import os

# Add project root and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.processor import TransactionProcessor

def main():
    print("Initializing TransactionProcessor...")
    # Adjust paths relative to root where script is run
    processor = TransactionProcessor()
    
    uploads_dir = 'data/uploads'
    
    if not os.path.exists(uploads_dir):
        print(f"Directory {uploads_dir} not found!")
        return

    count = 0
    for filename in os.listdir(uploads_dir):
        if not filename.endswith('.csv'):
            continue
            
        file_path = os.path.join(uploads_dir, filename)
        print(f"Processing {filename}...")
        
        # Infer Metadata
        owner = "Victor" # Default
        if "Larissa" in filename or "Inter" in filename:
            owner = "Larissa"
        
        # Infer Month Ref (YYYY-MM)
        import re
        match = re.search(r'(\d{4}-\d{2})', filename)
        if match:
            month_ref = match.group(1)
        else:
            # Fallback to current or skipping
            print(f"Skipping {filename}: Could not infer month reference (YYYY-MM).")
            continue
            
        with open(file_path, 'rb') as f:
            content = f.read()
            try:
                processor.process_file(content, filename, owner, month_ref)
                count += 1
                print(f"Successfully processed {filename} (Owner: {owner}, Month: {month_ref})")
            except Exception as e:
                print(f"Failed to process {filename}: {e}")

    print(f"Processing complete. Processed {count} files.")

if __name__ == "__main__":
    main()
