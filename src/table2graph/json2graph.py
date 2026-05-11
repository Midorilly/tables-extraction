import os
import sys
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.utils.schema import neo4j_query, neo4j_query_criteria

env_path = os.path.join(os.path.dirname(__file__), '../../neo4j.env')
load_dotenv(env_path)

# Neo4j connection parameters
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def aggregate_jsons_into_memory(base_dir: str):
    lot_master = {}

    for doc_folder in os.listdir(base_dir):
        doc_path = os.path.join(base_dir, doc_folder)
        if not os.path.isdir(doc_path): 
            continue
        
        for json_file in sorted(os.listdir(doc_path)):
            if not json_file.endswith('.json'): 
                continue

            file_path = os.path.join(doc_path, json_file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                continue
            
            document = doc_folder 
            
            for element in data.get('elementi', []):
                lot_numbers = element.get('numeri_lotto', [])
                if not lot_numbers:
                    lot_numbers = ["Generico"]
                
                for num in lot_numbers:
                    sub_lotto = str(element.get('sub_lotto') or '').strip()
                    key = f"{document}_{num}_{sub_lotto}"
                    
                    if key not in lot_master:
                        lot_master[key] = {
                            "documento": document,
                            "numero_lotto": num,
                            "sub_lotto": sub_lotto,
                            "codice_cig": set(),
                            "codice_cnd": set(),
                            "descrizioni": [],
                            "misure": set(),            
                            "confezionamento": set(),   
                            "fabbisogno_totale": element.get('fabbisogno_totale'),
                            "importo_base_asta": element.get('importo_base_asta'),
                            "strutture_destinatarie": set(),
                            "criteri_associati": []
                        }
                    
                    node = lot_master[key]
                    
                    # Some capitolati contain multiple tables for the same lot, one for the description, one for the criteria, etc. 
                    # Therefore, a merge of the data is necessary, avoiding overwriting and loss of information.
                    # Sets are used for cig, cnd, strutture, misure, confezionamento to avoid duplicates. 
                    # Descrizioni is a list to preserve order and allow duplicates if they differ.
                    if element.get('codice_cig'): node["codice_cig"].update(element['codice_cig'])
                    if element.get('codice_cnd'): node["codice_cnd"].update(element['codice_cnd'])
                    if element.get('strutture_destinatarie'): node["strutture_destinatarie"].update(element['strutture_destinatarie'])
                    
                    desc_lotto = element.get('descrizione_lotto')
                    if desc_lotto and desc_lotto not in node["descrizioni"]:
                        node["descrizioni"].append(desc_lotto)

                    misure = element.get('misure_dettagli_tecnici')
                    if misure: node["misure"].add(misure)

                    conf = element.get('confezionamento')
                    if conf: node["confezionamento"].add(conf)
                        
                    # Overwrite for fabbisogno_totale and importo_base_asta only if they are None, to preserve the first non-null value found
                    if node["fabbisogno_totale"] is None:
                        node["fabbisogno_totale"] = element.get('fabbisogno_totale')
                    if node["importo_base_asta"] is None:
                        node["importo_base_asta"] = element.get('importo_base_asta')

                    # Merge for criteri_associati: avoid duplicates based on 'parametro'
                    existing_criteria = {c['parametro'] for c in node["criteri_associati"]}
                    for c in element.get('criteri_associati', []):
                        if c['parametro'] not in existing_criteria:
                            node["criteri_associati"].append(c)

    # Sometimes there are tables with some important information (like criteri_associati) but without specific lot information (default set 'Generico')
    # In this case, we can try to "broadcast" the information from the generic node to all specific nodes of the same document, if they exist.
    generic_keys = [k for k in lot_master.keys() if lot_master[k]["numero_lotto"] == "Generico"]
    for key_gen in generic_keys:
        generic_node = lot_master[key_gen]
        current_doc = generic_node["documento"]
        
        # Find all specific nodes of the same document (same doc, different lot number) to broadcast the generic information
        specific_keys = [k for k in lot_master.keys() if lot_master[k]["documento"] == current_doc and k != key_gen]
        
        if specific_keys:
            # Broadcast the generic information to all specific nodes of the same document
            for key_spec in specific_keys:
                specific_node = lot_master[key_spec]
                specific_node["codice_cig"].update(generic_node["codice_cig"])
                specific_node["codice_cnd"].update(generic_node["codice_cnd"])
                specific_node["strutture_destinatarie"].update(generic_node["strutture_destinatarie"])
                specific_node["misure"].update(generic_node["misure"])
                specific_node["confezionamento"].update(generic_node["confezionamento"])
                
                for desc in generic_node["descrizioni"]:
                    if desc not in specific_node["descrizioni"]:
                        specific_node["descrizioni"].append(desc)
                        
                existing_criteria = {c['parametro'] for c in specific_node["criteri_associati"]}
                for c in generic_node["criteri_associati"]:
                    if c['parametro'] not in existing_criteria:
                        specific_node["criteri_associati"].append(c)
            
            # After broadcasting, we can safely remove the generic node
            del lot_master[key_gen]

    # Similar to "Generico", sometimes a lot appears without a sub_lotto in one table, 
    # but has specific sub_lotto assigned in other tables. We need to broadcast the info
    # from the generic lot (empty sub_lotto) to all specific sub_lots and delete it.
    empty_sublotto_keys = [k for k in lot_master.keys() if lot_master[k]["sub_lotto"] == ""]
    keys_to_delete = []
    for key_empty in empty_sublotto_keys:
        empty_node = lot_master[key_empty]
        current_doc = empty_node["documento"]
        current_num = empty_node["numero_lotto"]
        
        specific_keys = [
            k for k in lot_master.keys() 
            if lot_master[k]["documento"] == current_doc 
            and lot_master[k]["numero_lotto"] == current_num 
            and lot_master[k]["sub_lotto"] != ""
        ]
        
        if specific_keys:
            for key_spec in specific_keys:
                specific_node = lot_master[key_spec]
                specific_node["codice_cig"].update(empty_node["codice_cig"])
                specific_node["codice_cnd"].update(empty_node["codice_cnd"])
                specific_node["strutture_destinatarie"].update(empty_node["strutture_destinatarie"])
                specific_node["misure"].update(empty_node["misure"])
                specific_node["confezionamento"].update(empty_node["confezionamento"])
                
                if specific_node["fabbisogno_totale"] is None:
                    specific_node["fabbisogno_totale"] = empty_node["fabbisogno_totale"]
                if specific_node["importo_base_asta"] is None:
                    specific_node["importo_base_asta"] = empty_node["importo_base_asta"]
                
                for desc in empty_node["descrizioni"]:
                    if desc not in specific_node["descrizioni"]:
                        specific_node["descrizioni"].append(desc)
                        
                existing_criteria = {c['parametro'] for c in specific_node["criteri_associati"]}
                for c in empty_node["criteri_associati"]:
                    if c['parametro'] not in existing_criteria:
                        specific_node["criteri_associati"].append(c)
                        
            keys_to_delete.append(key_empty)
            
    for k in keys_to_delete:
        del lot_master[k]

    # Final cleanup: convert sets to lists and concatenate descriptions, misure, confezionamento for better readability in Neo4j.
    final_lots = []
    for k, v in lot_master.items():
        v["codice_cig"] = list(v["codice_cig"])
        v["codice_cnd"] = list(v["codice_cnd"])
        v["strutture_destinatarie"] = list(v["strutture_destinatarie"])
        v["descrizione_completa"] = " | ".join(v["descrizioni"])
        v["misure_dettagli"] = " | ".join(list(v["misure"]))
        v["confezionamento_dettagli"] = " | ".join(list(v["confezionamento"]))
        
        # Remove the intermediate fields that were used for merging but are not needed in Neo4j
        del v["descrizioni"]
        del v["misure"]
        del v["confezionamento"]
        
        final_lots.append(v)

    return final_lots


def populate_neo4j(driver, lots_to_load):
    with driver.session() as session:
        print(f"Loading {len(lots_to_load)} lots...")
        session.run(neo4j_query, batch=lots_to_load)
        print("Mapping Criteria relationships...")
        session.run(neo4j_query_criteria, batch=lots_to_load)

if __name__ == "__main__":
    # Il percorso base deve essere relativo alla root del progetto (da dove eseguiamo),
    # o potremmo calcolarlo rispetto a questo file.
    BASE_JSON_DIR = os.path.join(os.path.dirname(__file__), "../../data/json_normalized")
    
    refactored_lots = aggregate_jsons_into_memory(BASE_JSON_DIR)
    print(f"Found {len(refactored_lots)} unique Lotto nodes.")

    # Debug rapido salvando l'aggregato per ispezione visiva
    debug_path = "debug_lotti_aggregati.json"
    with open(debug_path, "w", encoding="utf-8") as x:
        json.dump(refactored_lots, x, indent=2, ensure_ascii=False)
    print(f"Salvato file di debug dell'aggregazione su {debug_path}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        populate_neo4j(driver, refactored_lots)
        print("Loading on Neo4j completed successfully!")
    except Exception as e:
        print(f"Error on DB: {e}")
    finally:
        driver.close()
