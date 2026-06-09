import os
import pandas as pd
from docling.document_converter import DocumentConverter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

PDF_DIR = os.path.join(PROJECT_ROOT, "data", "pdf", "capitolati")
BASE_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "extractions", "baseline", "docling_csv")
os.makedirs(BASE_OUT_DIR, exist_ok=True)

def run_baseline_extraction():
    if not os.path.exists(PDF_DIR):
        print(f"Directory non trovata: {PDF_DIR}")
        return

    # Model weights will be loaded automatically on first run
    converter = DocumentConverter()

    for pdf_filename in os.listdir(PDF_DIR):
        if not pdf_filename.lower().endswith('.pdf'):
            continue
            
        pdf_path = os.path.join(PDF_DIR, pdf_filename)
        doc_name = os.path.splitext(pdf_filename)[0]
        out_dir = os.path.join(BASE_OUT_DIR, doc_name)
        
        if os.path.exists(out_dir):
            for filename in os.listdir(out_dir):
                file_path = os.path.join(out_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        else:
            os.makedirs(out_dir, exist_ok=True)

        try:
            print(f"\n--- [BASELINE] Elaborazione di: {pdf_filename} ---")
            
            result = converter.convert(pdf_path)
            tables = result.document.tables
            print(f"Docling ha rilevato {len(tables)} tabelle.")
            
            for idx, table in enumerate(tables):
                # Page number
                page_num = 0
                if hasattr(table, "prov") and table.prov:
                    page_num = table.prov[0].page_no              
                # Docling to pandas DataFrame
                df = table.export_to_dataframe(doc=result.document)

                # Nan values are replaced with empty strings
                # The separator is set to ";" (same as plumber.py)
                df = df.fillna("")
                
                # Verify if the header is a fake pandas header (0, 1, 2, ...) and decide whether to save it or not
                has_fake_pandas_header = all(str(col).isdigit() for col in df.columns)
                save_header = not has_fake_pandas_header
                
                file_name = f"docling_tab_{idx + 1:03d}_pag_{page_num:03d}.csv"
                out_path = os.path.join(out_dir, file_name)
                
                df.to_csv(out_path, index=False, header=save_header, sep=";")
                
            print(f"Salvataggio completato in: {out_dir}")

        except Exception as e:
            print(f"Errore durante l'elaborazione di {pdf_filename}: {e}")

if __name__ == "__main__":
    run_baseline_extraction()