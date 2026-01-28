from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar
import sys

def dump_text(pdf_path):
    print(f"Dumping text from: {pdf_path}")
    try:
        pages = list(extract_pages(pdf_path))
        if not pages:
            print("No pages found.")
            return

        # Inspect ALL pages for the keywords
        for i, page in enumerate(pages):
            # print(f"--- Page {i + 1} ---") # Too verbose
            
            for element in page:
                if isinstance(element, LTTextContainer):
                    text = element.get_text()
                    stripped_txt = text.strip()
                    # Filter for keywords
                    if any(x in stripped_txt for x in ["Saldo Global", "10,000", "4,500", "Total de Apartados"]):
                         print(f"Page {i+1} Found: '{stripped_txt}' | bbox={element.bbox}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    path = r"D:\Mstar\4.MSN20251028359银行流水1_20251231问题单\MSN20251103038银行流水1\MSN20251103038银行流水1.pdf"
    if len(sys.argv) > 1:
        path = sys.argv[1]
    dump_text(path)
