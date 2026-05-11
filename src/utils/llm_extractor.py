import os
import json
import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MAX_ROWS_MINI = 50
MAX_COLS_MINI = 10

# These classes define the structured format for the extracted data. The LLM will be prompted to fill these fields based on the content of the CSV tables.
# Since the CSV tables are in Italian, the field names, descriptions, and prompts are also in Italian to improve extraction quality.
class Criterio(BaseModel):
    parametro: str = Field(description="Descrizione chiara del criterio di valutazione (es. morbidezza, assenza odore, traspirabilità)")
    punteggio_massimo: Optional[float] = Field(None, description="Punteggio massimo attribuibile. Estrai solo il valore numerico in formato standard (es. 15.5)")
    modalita_attribuzione: Optional[str] = Field(None, description="Lettera o formula (es. 'D', 'Q', 'Tabellare'). Se non presente, lascia null.")

class ElementoTabella(BaseModel):
    numeri_lotto: List[str] = Field(
        description="""ID o numeri del lotto. DISTINGUI ATTENTAMENTE tra range e liste discrete: 
        1) RANGE CONTINUI ('da', 'a', '-', 'al'): es. 'da 1 a 4' -> espandi in ['1', '2', '3', '4']. 
        2) LISTE DISCRETE ('e', ',', 'ed'): es. '1 e 4' -> estrai solo ['1', '4']. 
        Se il lotto manca, lascia lista vuota."""
    )

    sub_lotto: Optional[str] = Field(
        None, description="Eventuale specificazione di 'voce', 'sub-lotto', 'parte' o 'riga'. Indica SOLO il numero o la lettera: es. 'voce A' -> 'A', 'voce 1' -> '1', 'sublotto 2' -> '2'."
    )

    misure_dettagli_tecnici: Optional[str] = Field(
        None, description="Dimensioni, calibri, taglie o caratteristiche fisiche specifiche (es. '21 G x 40 mm', 'Siringa da 50 ml')."
    )

    confezionamento: Optional[str] = Field(
        None, description="Dettagli sull'imballo, campioni richiesti o numero di pezzi per confezione."
    )

    codice_cig: List[str] = Field(
        default_factory=list, 
        description="Codici identificativi di gara (CIG). Se più di uno, separali in una lista. Restituisci solo il codice alfanumerico."
    )

    codice_cnd: List[str] = Field(
        default_factory=list, 
        description="Classificazione Nazionale Dispositivi (CND). Solo il codice."
    )

    descrizione_lotto: Optional[str] = Field(None, description="Il nome del prodotto, descrizione dell'oggetto del lotto. INCLUDI QUI anche eventuali informazioni accessorie, note o specifiche aggiuntive che non rientrano negli altri campi, in modo da non perdere dettagli importanti presenti nella tabella.")
    
    fabbisogno_totale: Optional[float] = Field(
        None, description="Quantità o fabbisogno richiesto. Converti in numero puro. Es: '1.500 pz' -> 1500.0"
    )

    importo_base_asta: Optional[float] = Field(
        None, description="Importo a base d'asta. Converti stringhe italiane ('1.234,56 €') in float standard (1234.56)."
    )

    strutture_destinatarie: List[str] = Field(
        default_factory=list, 
        description="Nomi di ospedali, ASL, presidi o reparti (es. 'San Paolo', 'Loreto Nuovo') estratti dalle colonne."
    )

    criteri_associati: List[Criterio] = Field(
        default_factory=list, 
        description="Elenco dei criteri di valutazione associati a questo lotto, se esplicitati nella tabella."
    )

class TabellaNormalizzata(BaseModel):
    elementi: List[ElementoTabella]


def process_csv_to_json(raw_csv_text: str, doc_name: str, model_name: str = "gpt-4o-mini") -> Optional[dict]:
    system_prompt = """
    Sei un Data Engineer specializzato nella sanità pubblica italiana. Il tuo compito è estrarre informazioni strutturate da tabelle CSV provenienti da capitolati di gara medici.
    
    CONTESTO SUI DATI IN INGRESSO:
    - Ricevi il testo grezzo di un file CSV.
    - Il delimitatore di colonna è ESCLUSIVAMENTE il punto e virgola (;). 
    - Ignora qualsiasi virgola (,) usata come separatore: le virgole nel testo servono solo per i decimali o la punteggiatura.
    - Le tabelle talvolta sono disordinate, le intestazioni di colonna potrebbero essere fuse o implicite.

    REGOLE CRITICHE:
    1. RANGE VS LISTE DISCRETE DEI LOTTI: Presta la massima attenzione alle parole o ai simboli usati per separare i numeri di lotto!
       - RANGE (parole come "a", "al", trattino "-"): Se vedi "da 1 a 4", "1-4", espandi la sequenza (es. ["1", "2", "3", "4"]).
       - LISTE DISCRETE (parole come "e", virgola ","): Se vedi "1 e 4", "1, 4", estrai SOLO ["1", "4"].
       - SUBLOTTI: Quando indichi il sub_lotto devi indicare solo il numero o la lettera: es. 'voce A' diventa 'A', 'sublotto 2' diventa '2'.
    2. NUMERI ITALIANI: Gli importi usano il punto per le migliaia e la virgola per i decimali (es. "1.345,50 €"). Convertili in float standard (1345.50).
    3. ASSENZA DI DATI: Se un dato non è presente, restituisci null o []. Non inventare e non inserire N/A o simili.
    4. STRUTTURE DESTINATARIE: Se ci sono colonne con Ospedali e quantità in riga, estrai il nome dell'ospedale.
    5. CRITERI: Nei `criteri_associati` inserisci solo i reali criteri di valutazione della gara (es. qualità, prezzo). Non confondere i nomi dei reparti ospedalieri, l'allocazione logistica o i quantitativi totali per criteri e punteggi.
    6. NON ACCORPARE LE VOCI: Se una tabella ha più righe con lo stesso numero di lotto ma cambiano le "voci" (es. voce 1, voce 2) o le misure/dettagli tecnici, DEVI generare un ElementoTabella separato per ognuna di queste righe.
    7. INFORMAZIONI ACCESSORIE: Qualsiasi dettaglio, nota o informazione aggiuntiva presente nella tabella che non ha un campo strutturato specifico deve essere accorpata e salvata dentro la `descrizione_lotto`. Non tralasciare testo utile.
    """

    try:
        # with completions.parse, the LLM will directly return a structured object based on the TabellaNormalizzata schema.
        completion = client.beta.chat.completions.parse(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Documento: {doc_name}\n\nTesto CSV:\n{raw_csv_text}"}
            ],
            response_format=TabellaNormalizzata,
            temperature=0.0
        )
        parsed_data = completion.choices[0].message.parsed.model_dump()
        parsed_data["documento_sorgente"] = doc_name
        return parsed_data

    except Exception as e:
        print(f"\nError during LLM generation: {e}")
        return None


# Some tables are not useful, so before processing with the LLM, we show a preview of the first 5 rows and 8 columns to the user, along with the total number of rows and columns. 
# The user can then decide whether to proceed with the LLM extraction or skip that table.
def preview_table(csv_path: str):
    try:
        df = pd.read_csv(csv_path, sep=";", header=None, dtype=str).fillna("")
        print("\n" + "="*80)
        print(f"File: {os.path.basename(csv_path)}")
        print("-" * 80)
        print(df.head(5).iloc[:, :8].to_markdown(index=False))
        if df.shape[0] > 5 or df.shape[1] > 8:
            print(f"... (Table: {df.shape[0]} rows x {df.shape[1]} columns)")
        print("="*80)
        return True, df.shape[0], df.shape[1]
    except pd.errors.EmptyDataError:
        print(f"\nCSV file {csv_path} is empty. Skipping.")
        return False, 0, 0
    except Exception as e:
        print(f"\nError reading file {csv_path}: {e}")
        return False, 0, 0


if __name__ == "__main__":
    # set base directories relative to the script location 
    script_dir = os.path.dirname(os.path.abspath(__file__))
    BASE_IN_DIR = os.path.abspath(os.path.join(script_dir, "../../data/tables_exploration"))
    BASE_OUT_DIR = os.path.abspath(os.path.join(script_dir, "../../data/json_normalized"))
    os.makedirs(BASE_OUT_DIR, exist_ok=True)

    for doc_folder in sorted(os.listdir(BASE_IN_DIR)):
        doc_path = os.path.join(BASE_IN_DIR, doc_folder)
        # Skip files that are not directories (e.g. .DS_Store)
        if not os.path.isdir(doc_path): 
            continue

        out_doc_path = os.path.join(BASE_OUT_DIR, doc_folder)
        os.makedirs(out_doc_path, exist_ok=True)

        print(f"\nAnalyzing document: {doc_folder}")

        csv_files = sorted([f for f in os.listdir(doc_path) if f.endswith(".csv")])
        
        for csv_file in csv_files:
            in_csv_path = os.path.join(doc_path, csv_file)
            out_json_path = os.path.join(out_doc_path, csv_file.replace(".csv", ".json"))

            success, num_rows, num_cols = preview_table(in_csv_path)
            if not success:
                continue

            if num_rows > MAX_ROWS_MINI or num_cols > MAX_COLS_MINI:
                # For larger tables, we opt for the more powerful gpt-4o to ensure better extraction quality, while smaller tables can be processed with the more cost-effective gpt-4o-mini.
                target_model = "gpt-4o"
                print(f"({num_rows} rows, {num_cols} columns). Selected model: {target_model}")
            else:
                target_model = "gpt-4o-mini"
                print(f"({num_rows} rows, {num_cols} columns). Selected model: {target_model}")

            while True:
                choice = input(f"Do you want to process this table with the LLM? \ny for yes\nn for no\nq for quit: ").strip().lower()
                if choice in ['y', 'n', 'q']:
                    break
                print("Please enter 'y' for yes, 'n' for no, or 'q' for quit.")
            if choice == 'q':
                print("\nQuitting the script.")
                exit(0)
            
            if choice == 'y':
                with open(in_csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw_csv_text = f.read()
                
                print(f"Processing with LLM...")
                extracted_data = process_csv_to_json(raw_csv_text, doc_folder, target_model)

                if extracted_data:
                    with open(out_json_path, 'w', encoding='utf-8') as f:
                        json.dump(extracted_data, f, indent=2, ensure_ascii=False)
                    print(f"JSON saving completed in: {out_json_path}")
            else:
                print(f"Skipped by the user.")