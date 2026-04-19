import pdfplumber
import pandas as pd
import os
import re

PDF_PATH = "../../data/pdf/criteri/Allegato_8_Criteri_Abruzzo.pdf"
OUT_DIR  = "../../data/tables_exploration2"
os.makedirs(OUT_DIR, exist_ok=True)

# Some keywords that often indicate a "super-title" or category header that spans the entire width of the table
TITLE_BREAK_KEYWORDS = [
    'quadro economico', 'riepilogo', 'prospetto', 'totale complessivo',
]

# Some keywords that often indicate a new column header
HEADER_BREAK_KEYWORDS = [
    'giudizio', 'coefficiente', 'parametro', 'criterio',
    'lotto', 'voce', 'descrizione', 'quadro',
    'importo', 'totale', 'oneri', 'sicurezza', 'iva',
    'ribasso', "base d'asta", 'somme', 'art.',
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
                    str(c).strip().replace('.', '', 1).isdigit()
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

def split_tables_by_super_titles(tables):
    """Split tables that contain multiple "super-title" rows (rows with only 1 non-empty cell) which likely indicate category headers."""
    
    split_tables_list = []
    
    for table_info in tables:
        df = table_info["data"]
        if df.empty:
            split_tables_list.append(table_info)
            continue
        
        # Identify all rows that look like super-titles (only 1 non-empty cell) and are followed within the next 3 rows by a "data row" (with > 1 non-empty cells)
        super_title_indices = []
        for idx in range(len(df)):
            row = df.iloc[idx]
            non_empty_cells = [c for c in row if pd.notna(c) and str(c).strip() != ""]
            
            # Check if the previous row was a super-title to avoid splitting on consecutive super-titles that likely belong to the same header block
            prev_was_single = False
            if idx > 0:
                prev_row = df.iloc[idx - 1]
                prev_non_empty = [c for c in prev_row if pd.notna(c) and str(c).strip() != ""]
                if len(prev_non_empty) == 1:
                    prev_was_single = True
            
            # A super-title is a row with only 1 non-empty cell, but we only consider it a valid split point if within the next 3 rows we find a "data row" with more than 1 non-empty cell, 
            # to avoid splitting on rows that are just part of a multi-line header.
            if len(non_empty_cells) == 1 and pd.notna(row.iloc[0]) and str(row.iloc[0]).strip() != "" and not prev_was_single:
                # Look ahead in the next 3 rows to see if we find a data row with more than 1 non-empty cell
                found_data_row = False
                for forward_idx in range(idx + 1, min(idx + 4, len(df))):
                    future_row = df.iloc[forward_idx]
                    future_non_empty = [c for c in future_row if pd.notna(c) and str(c).strip() != ""]
                    if len(future_non_empty) > 1:
                        found_data_row = True
                        break
                
                if found_data_row:
                    super_title_indices.append(idx)
        
        # If there are 0 or 1 super-title indices, or if the only super-title is at the very top of the table, we assume this table doesn't need to be split
        if len(super_title_indices) <= 1 and not (len(super_title_indices) == 1 and super_title_indices[0] > 0):
            split_tables_list.append(table_info)
            continue
            
        # Define the first category index as the first super-title index that is not at the very top of the table 
        # (if the first super-title is at index 0, we skip it and take the next one as the first category index)
        if len(super_title_indices) > 0 and super_title_indices[0] == 0:
            if len(super_title_indices) < 2:
                split_tables_list.append(table_info)
                continue
            first_category_idx = super_title_indices[1]
            category_indices = super_title_indices[1:]
        else:
            first_category_idx = super_title_indices[0]
            category_indices = super_title_indices
            
        # The common header is everything that comes before the first category
        common_header_df = df.iloc[:first_category_idx]
        
        new_tables_created = False
        for i, start_idx in enumerate(category_indices):
            end_idx = category_indices[i+1] if i + 1 < len(category_indices) else len(df)
            sub_df = df.iloc[start_idx:end_idx]
            
            # Merge the common header with the sub-table, aligning columns by position and filling missing columns with NaN
            combined_df = pd.concat([common_header_df, sub_df], ignore_index=True)
            
            new_t_info = table_info.copy()
            new_t_info["data"] = combined_df
            split_tables_list.append(new_t_info)
            new_tables_created = True
            
        if not new_tables_created:
            split_tables_list.append(table_info)

    print(f"Divisione completata. Le tabelle sono passate da {len(tables)} a {len(split_tables_list)}.")
    return split_tables_list

def split_tables_after_totale(tables):
    """Split tables after any row that contains only the word 'totale' in any column."""
    split_list = []
    for table_info in tables:
        df = table_info["data"]
        if df.empty:
            split_list.append(table_info)
            continue
            
        last_split_idx = 0
        for idx in range(len(df)):
            row_has_totale = False
            for cell in df.iloc[idx]:
                if pd.notna(cell) and str(cell).strip().lower() == 'totale':
                    row_has_totale = True
                    break
            
            if row_has_totale:
                # Split the table at this point, including the "totale" row in the first part
                sub_df = df.iloc[last_split_idx:idx + 1]
                if not sub_df.empty:
                    new_info = table_info.copy()
                    new_info["data"] = sub_df
                    split_list.append(new_info)
                last_split_idx = idx + 1
        
        # Add any remaining part of the table after the last "totale" split
        if last_split_idx < len(df):
            sub_df = df.iloc[last_split_idx:]
            if not sub_df.empty:
                new_info = table_info.copy()
                new_info["data"] = sub_df
                split_list.append(new_info)

    print(f"Divisione post-'totale' completata. Le tabelle sono passate da {len(tables)} a {len(split_list)}.")
    return split_list

def filter_invalid_tables(tables):
    """Filter out tables that are essentially just a single row or a single column after dropping empty cells."""
    valid_tables = []
    for table_info in tables:
        df = table_info["data"]
        
        # Sostituisce stringhe vuote con NA per usare dropna
        cleaned_df = df.replace(r'^\s*$', pd.NA, regex=True).dropna(how='all', axis=0).dropna(how='all', axis=1)
        
        # Se dopo la pulizia rimane 1 o 0 righe, oppure 1 o 0 colonne, la eliminiamo
        if cleaned_df.shape[0] <= 1 or cleaned_df.shape[1] <= 1:
            continue
            
        valid_tables.append(table_info)
        
    print(f"Filtraggio completato. Le tabelle valide finali sono {len(valid_tables)}.")
    return valid_tables

def save_tables_for_inspection(tables):
    for idx, table_info in enumerate(tables):
        page_start = table_info["page_num"]
        page_end   = table_info.get("page_num_end", page_start)
        df = table_info["data"].replace(pd.NA, "")

        if page_start == page_end:
            file_name = f"tab_{idx:03d}_pag_{page_start:03d}.csv"
        else:
            file_name = f"tab_{idx:03d}_pag_{page_start:03d}_a_{page_end:03d}.csv"

        out_path = os.path.join(OUT_DIR, file_name)
        df.to_csv(out_path, index=False, header=False, sep=";")


if __name__ == "__main__":
    try:
        for filename in os.listdir(OUT_DIR):
            os.remove(os.path.join(OUT_DIR, filename))

        raw_tables = extract_all_raw_tables(PDF_PATH)
        valid_tables = filter_invalid_tables(raw_tables)
        merged_tables = merge_continuation_tables(valid_tables)
        split_tables = split_tables_by_super_titles(merged_tables)
        tot_split_tables = split_tables_after_totale(split_tables)
        final_tables = filter_invalid_tables(tot_split_tables)
        save_tables_for_inspection(final_tables)

    except FileNotFoundError:
        print(f"File non trovato: {PDF_PATH}")