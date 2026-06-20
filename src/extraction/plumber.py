import pdfplumber
import pandas as pd
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

PDF_DIR = os.path.join(PROJECT_ROOT, "data", "pdf", "capitolati")
BASE_OUT_DIR = os.path.join(PROJECT_ROOT, "data", "extractions", "custom", "pdfplumber_csv")
os.makedirs(BASE_OUT_DIR, exist_ok=True)

# Some keywords that often indicate a new column header
HEADER_BREAK_KEYWORDS = [
    'giudizio', 'coefficiente', 'parametro', 'criterio', 'criteri', 'punteggio',
    'lotto', 'voce', 'descrizione', 'quadro',
    'importo', 'totale', 'oneri', 'sicurezza', 'iva',
    'ribasso', "base d'asta", 'somme', 'art.',
    'presidio', 'presidi', 'reparto', 'reparti', 'struttura', 'strutture', 'numero'
]

# Pdfplumber extraction 
def extract_all_raw_tables(filepath):
    raw_tables = []
    print(f"Apertura del documento: {filepath}")
    with pdfplumber.open(filepath) as pdf:
        for i, page in enumerate(pdf.pages):
            for t_idx, table in enumerate(page.extract_tables()):
                cleaned_rows = []
                for row in table:
                    if any(cell is not None and str(cell).strip() != "" for cell in row):
                        cleaned_rows.append(
                            [re.sub(r'\s+', ' ', str(c).strip()) if c else "" for c in row]
                        )
                if cleaned_rows:
                    df = pd.DataFrame(cleaned_rows).replace(r'^\s*$', pd.NA, regex=True)
                    raw_tables.append({
                        "page_num": i + 1,
                        "table_idx_on_page": t_idx + 1,
                        "data": df
                    })
    print(f"\nEstrazione completata. Trovate in totale {len(raw_tables)} tabelle valide.")
    return raw_tables

# Helper functions
def has_super_title(df):
    """True if the first row of the DataFrame looks like a super-title (only 1 non-empty cell)"""
    if df.empty:
        return False
    first_row = df.iloc[0]
    return first_row.notna().sum() == 1 and df.shape[1] > 1


def align_and_concat(current_df, next_df):
    """Align next_df to current_df based on the last row of current_df and the first row of next_df, then concatenate.
    This is a heuristic approach to handle cases where the number of columns differs due to misalignment."""
    
    # CASE A: same number of columns → just concatenate
    if current_df.shape[1] == next_df.shape[1]:
        next_df.columns = current_df.columns
        return pd.concat([current_df, next_df], ignore_index=True)

    # CASE B: next_df has fewer columns → try to align based on the last row of current_df
    elif next_df.shape[1] < current_df.shape[1]:
        last_row = current_df.iloc[-1]
        active_cols = [
            col for col in current_df.columns
            if pd.notna(last_row[col]) and str(last_row[col]).strip() != ""
        ]
        aligned_df = pd.DataFrame(columns=current_df.columns)

        # if the number of active columns matches next_df, we can directly align by position
        if len(active_cols) == next_df.shape[1]:
            for i, col in enumerate(active_cols):
                aligned_df[col] = next_df.iloc[:, i].values

        # otherwise, we just place next_df in the leftmost columns and leave the rest as NaN
        else:
            for i in range(next_df.shape[1]):
                aligned_df.iloc[:, i] = next_df.iloc[:, i].values
        return pd.concat([current_df, aligned_df], ignore_index=True)

    else:
        return pd.concat([current_df, next_df], ignore_index=True)


def merge_continuation_tables(raw_tables):
    """Merge tables that are likely continuations of each other based on page numbers, header similarity, and presence of super-titles.
    This is helpful to handle cases where a single logical table is split across multiple pages or multiple table blocks."""
    
    if not raw_tables:
        return []
    
    merged_tables = []
    current_table = raw_tables[0]
    current_df = current_table["data"]

    for next_table in raw_tables[1:]:
        next_df = next_table["data"]
        is_continuation = False

        current_end_page = current_table.get("page_num_end", current_table["page_num"])
        is_same_page = (next_table["page_num"] == current_end_page)
        is_next_page = (next_table["page_num"] == current_end_page + 1)

        if is_next_page or is_same_page:
            current_first_row_text = " ".join(
                str(x).lower() if pd.notna(x) else ""
                for x in current_df.iloc[0].tolist()
            )
            next_first_row_text = " ".join(
                str(x).lower() if pd.notna(x) else ""
                for x in next_df.iloc[0].tolist()
            )

            # CASE A: identical header, don't merge
            if current_first_row_text == next_first_row_text and len(next_first_row_text.strip()) > 0:
                is_continuation = False

            # CASE B: different header → check if it's a new header
            else:
                looks_like_new_header = False
                
                # check only the first row, or the second if the first is a super-title
                row_indices_to_check = [0]
                if has_super_title(next_df) and len(next_df) > 1:
                    row_indices_to_check.append(1)
                    
                for row_idx in row_indices_to_check:
                    row_text = " ".join(
                        str(x).lower() if pd.notna(x) else ""
                        for x in next_df.iloc[row_idx].tolist()
                    )
                    
                    for kw in HEADER_BREAK_KEYWORDS:
                        # Search for the keyword as a whole word and punctuation boundary in the row text
                        pattern = r'(?:\b|^)' + re.escape(kw) + r'(?:\b|\W|$)'
                        if re.search(pattern, row_text):
                            looks_like_new_header = True
                            break
                    if looks_like_new_header:
                        break
                        
                # Check has_pure_number on the row that might be data
                row_for_number = 1 if (has_super_title(next_df) and len(next_df) > 1) else 0
                next_first_row_list = [
                    str(x).lower() if pd.notna(x) else ""
                    for x in next_df.iloc[row_for_number].tolist()
                ]
                has_pure_number = any(
                    (str(c).strip().replace('.', '', 1).isalnum() and any(char.isdigit() for char in str(c)))
                    for c in next_first_row_list if str(c).strip() != ""
                )
                
                if not looks_like_new_header or has_pure_number:
                    is_continuation = True

        # Merge if it's a continuation, otherwise finalize the current table and start a new one
        if is_continuation and not next_df.empty:
            current_df = align_and_concat(current_df, next_df)
            current_table["page_num_end"] = next_table["page_num"]
        else:
            current_table["data"] = current_df
            merged_tables.append(current_table)
            current_table = next_table
            current_df = next_table["data"]

    current_table["data"] = current_df
    merged_tables.append(current_table)
    print(f"Fusione completata. Le tabelle sono passate da {len(raw_tables)} a {len(merged_tables)}.")
    return merged_tables

def split_tables_after_totale(tables):
    """Split tables after any row containing the word 'totale' (accommodating strings like 'totale complessivo' or 'totale glucometri'), skipping header rows."""
    
    def is_header_like_row(row):
        cells = [str(c).strip().lower() for c in row if pd.notna(c) and str(c).strip() != ""]
        if not cells:
            return False

        row_text = " ".join(cells)
        
        # Check if the row contains any of the header keywords as whole words (not as part of another word), which is a strong signal that it's an actual header row and not a "totale" row.
        has_header_keyword = any(
            re.search(r'(?:\b|^)' + re.escape(kw) + r'(?:\b|\W|$)', row_text)
            for kw in HEADER_BREAK_KEYWORDS
        )
        
        # Check if the row has a significant amount of text (e.g., more than 40 characters when non-alphabetic characters are removed), which can indicate it's a descriptive header rather than a data row with "totale".
        text_only = re.sub(r'[^a-z]', '', row_text)
        is_text_heavy = len(text_only) > 40
        
        return has_header_keyword and is_text_heavy

    split_list = []
    for table_info in tables:
        df = table_info["data"]
        if df.empty:
            split_list.append(table_info)
            continue
            
        last_split_idx = 0
        in_totale_block = False
        
        for idx in range(len(df)):
            row_has_totale = False
            row = df.iloc[idx]
            
            # If we are in the first 2 rows, or if the row looks like a header, we skip the "totale" check to avoid splitting on header rows that might contain the word "totale" as part of a descriptive title. We only want to trigger splits on actual data rows that contain "totale".
            row_is_header = (idx < 2) or is_header_like_row(row)

            if not row_is_header:
                for cell in row:
                    if pd.notna(cell):
                        cell_text = str(cell).strip().lower()
                        # Trigger the split if the cell explicitly STARTS with "totale", "iva", "imposta" etc.
                        # so that rows like "IVA 22%" interspersed between "Totale" rows are kept in the same block
                        if cell_text.startswith(('totale', 'iva', 'imposta', 'sconto', 'ribasso')) and len(cell_text) < 40:
                            row_has_totale = True
                            break
            
            if row_has_totale:
                in_totale_block = True
            elif in_totale_block:
                # We just exited a block of "totale" rows. Split the table right before this current row.
                sub_df = df.iloc[last_split_idx:idx]
                if not sub_df.empty:
                    new_info = table_info.copy()
                    new_info["data"] = sub_df
                    split_list.append(new_info)
                last_split_idx = idx
                in_totale_block = False
        
        # Add any remaining part of the table
        if last_split_idx < len(df):
            sub_df = df.iloc[last_split_idx:]
            if not sub_df.empty:
                new_info = table_info.copy()
                new_info["data"] = sub_df
                split_list.append(new_info)

    print(f"Divisione post-'totale' completata. Le tabelle sono passate da {len(tables)} a {len(split_list)}.")
    return split_list

def compress_staggered_columns(df):
    """
    Realign staggered columns (a common issue with joined cells) by merging them together if and only if they never overlap in the same row.
    """
    
    # Remove empty columns first to avoid confusion in the merging logic
    df_clean = df.replace(r'^\s*$', pd.NA, regex=True).dropna(how='all', axis=1)
    if df_clean.empty:
        return df_clean
        
    cols = list(df_clean.columns)
    if not cols:
        return df_clean
        
    merged = []
    current_col = df_clean[cols[0]].copy()

    def looks_like_hierarchy_boundary(left_col, right_col):
        """Return True when the two columns look like a main-item / sub-item structure and should not be compressed."""
        left_values = [str(v).strip().lower() for v in left_col if pd.notna(v) and str(v).strip() != ""]
        right_values = [str(v).strip().lower() for v in right_col if pd.notna(v) and str(v).strip() != ""]

        if not left_values or not right_values:
            return False

        # Main rows often start with numeric identifiers like 6, 7, 8.
        left_numeric_ids = sum(v.isdigit() for v in left_values)
        # Sub-rows often start with single letters like a, b, c or 1a, 1b or roman numerals or 1.1, 1.2 etc
        right_letter_ids = sum(len(v) == 1 and v.isalpha() for v in right_values)
        right_composite_ids = sum(len(v) > 1 and v[0].isdigit() and v[1].isalpha() for v in right_values)
        right_roman_ids = sum(re.match(r'^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$', v) is not None for v in right_values)
        right_dot_ids = sum(re.match(r'^\d+\.\d+$', v) is not None for v in right_values)

        if left_numeric_ids / len(left_values) >= 0.5 and right_letter_ids / len(right_values) >= 0.5:
            return True

        return False
    
    
    for i in range(1, len(cols)):
        next_col = df_clean[cols[i]]
        
        # There is an overlap if there is at least one row where both current_col and next_col have non-NA values
        overlap = (current_col.notna() & next_col.notna()).any()
        
        if not overlap and not looks_like_hierarchy_boundary(current_col, next_col):
            # If there is no overlap, we can safely merge the two columns by filling NA values in current_col with values from next_col
            current_col = current_col.combine_first(next_col)
        else:
            # If they collide, they are actually two distinct columns. Close the current one and move to the next
            merged.append(current_col)
            current_col = next_col.copy()
            
    merged.append(current_col)
    res = pd.concat(merged, axis=1)
    res.columns = range(res.shape[1])
    return res

def remove_consecutive_duplicates(df):
    """
    Delete consecutive duplicate rows in the DataFrame, keeping only the first occurrence. 
    """
    if df.empty:
        return df
    
    # Create a mask that is True for rows that are different from the previous row, and False for rows that are identical to the previous row.
    mask = (df != df.shift(1)).any(axis=1)
    # Keep only the rows where the mask is True, which means they are different from the previous row, and reset the index.
    return df[mask].reset_index(drop=True)

def filter_invalid_tables(tables):
    """Filter out tables that are essentially just a single row or a single column after dropping empty cells."""
    valid_tables = []
    for table_info in tables:
        df = table_info["data"]
        
        # Replace empty strings with NA and drop rows and columns that are entirely NA to identify tables that are effectively empty or just a single row/column of data
        cleaned_df = df.replace(r'^\s*$', pd.NA, regex=True).dropna(how='all', axis=0).dropna(how='all', axis=1)
        
        # If after cleaning the table has 1 or fewer rows or columns, it's not a valid table for our purposes
        if cleaned_df.shape[0] <= 1 or cleaned_df.shape[1] <= 1:
            continue
            
        valid_tables.append(table_info)
        
    print(f"Filtraggio completato. Le tabelle valide finali sono {len(valid_tables)}.")
    return valid_tables

def save_tables_for_inspection(tables, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for idx, table_info in enumerate(tables):
        page_start = table_info["page_num"]
        page_end   = table_info.get("page_num_end", page_start)
        df = table_info["data"].replace(pd.NA, "")

        if page_start == page_end:
            file_name = f"tab_{idx + 1:03d}_pag_{page_start:03d}.csv"
        else:
            file_name = f"tab_{idx + 1:03d}_pag_{page_start:03d}_{page_end:03d}.csv"

        out_path = os.path.join(out_dir, file_name)
        df.to_csv(out_path, index=False, header=False, sep=";")


if __name__ == "__main__":
    if not os.path.exists(PDF_DIR):
        print(f"Directory non trovata: {PDF_DIR}")
        exit()

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
            print(f"\n--- Elaborazione di: {pdf_filename} ---")
            raw_tables = extract_all_raw_tables(pdf_path)
            valid_tables = filter_invalid_tables(raw_tables)
            
            # Apply column compression to all valid tables before merging, to handle cases where the same logical column is split into multiple staggered columns due to joined cells
            for t in valid_tables:
                t["data"] = compress_staggered_columns(t["data"])
                t["data"] = remove_consecutive_duplicates(t["data"])
            
            merged_tables = merge_continuation_tables(valid_tables)
            tot_split_tables = split_tables_after_totale(merged_tables)
                
            final_tables = filter_invalid_tables(tot_split_tables)
            save_tables_for_inspection(final_tables, out_dir)
            print(f"Tabelle salvate in: {out_dir}")

        except Exception as e:
            print(f"Errore durante l'elaborazione di {pdf_filename}: {e}")