# Spiegazione di `plumber.py`

Il file `plumber.py` rappresenta il cuore della pipeline di estrazione, pulizia e strutturazione delle tabelle provenienti dai file PDF. 
Dato che l'estrazione di tabelle dai PDF è un'operazione complessa e soggetta ad artefatti (celle unite, tabelle spezzate su più pagine, intestazioni annidate), lo script applica una serie di euristiche sequenziali basate sulla libreria `pdfplumber` e manipolazioni via `pandas`.

## Flusso di Lavoro (Pipeline)

L'elaborazione di un singolo PDF segue questi passaggi in ordine logico:

### 1. Estrazione Grezza (`extract_all_raw_tables`)
Lo script apre il PDF e itera su ogni pagina estraendo le tabelle. Durante l'estrazione:
- Sostituisce gli spazi multipli (come `\n` o tabulazioni interne) con un singolo spazio.
- Le righe completamente vuote vengono scartate.
- Se la tabella ha dati, viene convertita in un `DataFrame` di pandas, sostituendo le celle vuote con `pd.NA`.
- L'output è una lista di dizionari, ognuno contenente i dati della tabella e i metadati sulla pagina.

### 2. Filtraggio delle Tabelle Invalide (`filter_invalid_tables`)
Spesso i PDF espongono artefatti di layout (come linee decorative) che `pdfplumber` interpreta come tabelle. 
Questa funzione rimuove tutte quelle tabelle che, al netto delle celle vuote, risultano avere **una sola riga o una sola colonna**, riducendo drasticamente il rumore e i falsi positivi.

### 3. Compressione delle Colonne Sfalsate (`compress_staggered_columns`)
Se la libreria estrae il testo suddividendolo su due o più colonne (in cui una colonna ha dei valori `NA` dove l'altra ha dati, e viceversa), la funzione **fonde le colonne assieme**. 
La fusione avviene solo quando le colonne non hanno collisioni, cioè quando non esiste alcuna riga in cui entrambe contengono un valore valido contemporaneamente.
In più, il merge viene evitato quando la coppia di colonne sembra rappresentare una gerarchia padre/figlio, per esempio una colonna con identificativi numerici principali e una con sotto-voci alfabetiche o composte.

### 4. Rimozione dei Duplicati (`remove_consecutive_duplicates`)
L'estrazione da PDF può generare righe identiche adiacenti, specialmente in presenza di celle multi-line. Questa funzione pulisce la tabella mantenendo solo la prima occorrenza di righe identiche continue.

### 5. Fusione tra Pagine (Merge) (`merge_continuation_tables`)
Se una singola tabella logica viene stampata a cavallo tra due o più pagine, `pdfplumber` la interpreta come tabelle separate. Questa funzione si occupa di ricucirle.
- **Continuità:** Valuta se le tabelle sono su pagine adiacenti (o nella stessa pagina).
- **Nuove Intestazioni vs Dati:** Controlla la prima riga della tabella successiva. Cerca di capire se si tratta di un **nuovo header** controllando la presenza di parole chiave note (`HEADER_BREAK_KEYWORDS` come 'lotto', 'criteri', 'importo', ecc.).
- **Controllo Numerico:** Verifica se la riga "sospetta" contiene stringhe alfanumeriche o numeriche attaccate (come Codici CIG o Importi) escludendo spazi e parole pure. Se sì, capisce che si tratta di *dati* (continuazione) e non di una nuova intestazione, unendo le tabelle.
- **Riallineamento (`align_and_concat`):** Se per via del formato le due porzioni della tabella hanno un numero diverso di colonne, la funzione cerca di incastrarle spingendo la tabella scarna a sinistra oppure mappando l'indice delle colonne valide nell'ultima riga della porzione precedente.

### 6. Divisione post "Totale" (`split_tables_after_totale`)
Alcuni blocchi finali delle tabelle (riepiloghi) contengono filotti di righe che iniziano con "Totale", "IVA", "Imposta", "Sconto".
Dopo che il blocco dei "Totali" finisce e inizia nuovamente un set di righe dati normali, lo script divide la tabella per separarli in entità logiche distinte, così che i "Totali" chiudano in bellezza le tabelle di pertinenza.

### 7. Filtro Definitivo e Salvataggio (`save_tables_for_inspection`)
- Esegue un'ultima passata di `filter_invalid_tables` per pulire i residui prodotti dagli step di spezzamento.
- Salva ogni tabella estratta come file `.csv` nominandola appropriatamente in base alla tabella origine e all'intervallo di pagine da cui è stata presa (es. `tab_000_pag_001_a_002.csv`). Il separatore dei campi è il `;` e i valori `NA` di pandas vengono trasformati in stringhe vuote.

## Dizionari e Configurazioni

Nella parte superiore del file, lo script si appoggia su costanti cruciali:
* `HEADER_BREAK_KEYWORDS`: per individuare intestazioni che bloccano le fusioni indesiderate tra tabelle concettualmente diverse o che aiutano a capire che è iniziata una matrice nuova. 
