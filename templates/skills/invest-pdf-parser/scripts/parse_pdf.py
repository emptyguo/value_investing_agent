import argparse
import sys
import os

try:
    import opendataloader_pdf
except ImportError:
    print("Error: opendataloader_pdf is not installed.")
    print("Please run: pip install opendataloader-pdf")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Parse PDF to Markdown using opendataloader-pdf")
    parser.add_argument("--input", required=True, help="Path to PDF file")
    parser.add_argument("--output-dir", required=False, help="Directory to save the markdown")
    parser.add_argument("--hybrid", action="store_true", help="Use hybrid AI mode for complex tables/charts")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
         print(f"Error: File not found: {input_path}")
         sys.exit(1)
         
    out_dir = args.output_dir
    if not out_dir:
        out_dir = os.path.dirname(input_path)
    out_dir = os.path.abspath(out_dir)
    
    # Process
    try:
        if args.hybrid:
            print("Using Hybrid AI Mode (Requires backend server processing)...")
            opendataloader_pdf.convert(
                input_path=[input_path],
                output_dir=out_dir,
                format="markdown",
                hybrid="docling-fast"
            )
        else:
            print("Using Deterministic Local Mode...")
            opendataloader_pdf.convert(
                input_path=[input_path],
                output_dir=out_dir,
                format="markdown"
            )
        
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        md_path = os.path.join(out_dir, f"{base_name}.md")
        
        print("\nSuccess!")
        print(f"Original PDF : {input_path}")
        print(f"Markdown out : {md_path}")
        
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
