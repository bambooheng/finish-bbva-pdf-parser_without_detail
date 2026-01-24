import fitz
import sys
import os

pdf_path = r"D:\完成版_finish\bbva-pdf-parser_除流水明细外其他部分\inputs\BBVA JUN-JUL真实1-MSN20251016154.pdf"
output_path = "debug_text.txt"

print(f"Reading {pdf_path}...")
try:
    doc = fitz.open(pdf_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(doc):
            if i >= 5: break # Only first 5 pages
            
            # Use 'layout' to preserve some positioning
            text = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            
            header = f"\n\n--- PAGE {i+1} ---\n\n"
            print(header)
            # print(text) # Don't print everything to stdout to avoid clutter
            f.write(header)
            f.write(text)
            
    print(f"\nText written to {output_path}")

except Exception as e:
    print(f"Error: {e}")
