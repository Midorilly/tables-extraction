import os
import json
from dotenv import load_dotenv
from langchain_community.graphs import Neo4jGraph
from langchain_openai import ChatOpenAI
from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_community.chains.graph_qa.prompts import CYPHER_GENERATION_PROMPT
from langchain_core.prompts import PromptTemplate

load_dotenv(override=True)

graph = Neo4jGraph(
    url=os.getenv("NEO4J_URI"),
    username=os.getenv("NEO4J_USERNAME"),
    password=os.getenv("NEO4J_PASSWORD")
)

llm = ChatOpenAI(model="gpt-4o", temperature=0.0)

custom_template = CYPHER_GENERATION_PROMPT.template + """
CRITICAL RULES AND EXAMPLES FOR THIS MEDICAL DATABASE:

1. STEMMING (MANDATORY): Always extract max 4-5 letters of keywords and use `AND`. 
   DO NOT USE `OR`.
   Correct Example: `WHERE toLower(l.descrizione) CONTAINS 'siri' AND toLower(l.descrizione) CONTAINS 'sott'`

2. CIG AND CND ONTOLOGY (MANDATORY): CIG and CND are leaf nodes. They NEVER connect to each other. They both connect to Lotto or SubLotto.
   Correct Example: `MATCH (l)-[:HA_CIG]->(cig:CIG {{codice: '123'}}) MATCH (l)-[:HA_CND]->(c:CND) RETURN c.codice`

3. SUBLOTTO HANDLING (MANDATORY): Sublots (e.g. "Lotto 3B") often don't have their own properties. If you query a Sublotto, always extract properties from the parent Lotto if missing.
   Correct Example: `MATCH (l:Lotto {{id_lotto: '2'}})-[:HA_SUBLOTTO]->(s:SubLotto {{sub_lotto: 'C'}}) RETURN l.importo_base_asta / s.fabbisogno_totale`

4. CRITERIA RELATIONSHIP (MANDATORY): You must use the `r` variable for scores.
   Correct Example: `MATCH (l)-[r:SI_VALUTA_CON]->(c:Criterio) RETURN c.parametro, r.punteggio_massimo, r.dettagli_valutazione`

5. AVOID 'DESCRIZIONE' FOR LOT NUMBERS: Never search for a lot number inside the text description.
   Correct Example: `WHERE l.id_lotto = '2'`

6. IGNORE CONTEXT WORDS: If the user asks for "prodotti", "dispositivi", "valutate", DO NOT put these words in the `CONTAINS` clause. Only match the actual medical item (e.g. 'siring', 'ago', 'garz').
"""

cypher_prompt = PromptTemplate(
    input_variables=["schema", "question"], 
    template=custom_template
)

cypher_chain = GraphCypherQAChain.from_llm(
    cypher_llm=llm,
    qa_llm=llm,
    graph=graph,
    verbose=True, #verbose=True useful for debugging
    cypher_prompt=cypher_prompt,
    allow_dangerous_requests=True
)

def run_automated_benchmark(input_jsonl_path, output_json_path):
    benchmark_results = []
    
    if not os.path.exists(input_jsonl_path):
        print(f"The input file '{input_jsonl_path}' does not exist. Please check the path and try again.")
        return

    with open(input_jsonl_path, "r", encoding="utf-8") as f:
        query_id = 1
        for idx, line in enumerate(f, 1):
            line = line.strip()
            # Skip empty lines and comments (lines starting with //)
            if not line or line.startswith("//"):
                continue
                
            try:
                data = json.loads(line)
                user_query = data.get("query")
                expected_answer = data.get("answer")
                sources = data.get("sources", [])
                
                print(f"\nDOMANDA: {user_query}")
                print(f"Atteso: {expected_answer}")
                
                response = cypher_chain.invoke({"query": user_query})
                generated_result = response.get("result")
                
                # Results
                benchmark_results.append({
                    "id": query_id,
                    "query": user_query,
                    "expected_answer": expected_answer,
                    "generated_answer": generated_result,
                    "sources": sources,
                    "status": "SUCCESS"
                })
                print(f"-> Risultato: {generated_result}")
                query_id += 1

            except Exception as e:
                print(f"Error processing line {idx}: {e}")
                benchmark_results.append({
                    "id": query_id,
                    "query": user_query if 'user_query' in locals() else "Corrupted line",
                    "expected_answer": expected_answer if 'expected_answer' in locals() else "",
                    "generated_answer": None,
                    "error_details": str(e),
                    "status": "FAILED"
                })
                query_id += 1

    with open(output_json_path, "w", encoding="utf-8") as out_f:
        json.dump(benchmark_results, out_f, indent=2, ensure_ascii=False)
        
    print(f"\nResults saved to: {output_json_path}")

if __name__ == "__main__":
    INPUT_FILE = os.path.join(os.path.dirname(__file__), "GraphRAG.jsonl") 
    OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "rag_results.json")
    
    run_automated_benchmark(INPUT_FILE, OUTPUT_FILE)