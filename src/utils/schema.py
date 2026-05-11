neo4j_query = """
    UNWIND $batch AS lotto
    
    // Nodo Documento Gara
    MERGE (doc:DocumentoGara {id: lotto.documento})
    
    // Nodo Lotto Padre (Identificato solo dal Documento e dal Numero)
    MERGE (lotto_padre:Lotto {doc_id: lotto.documento, id_lotto: lotto.numero_lotto})
    
    // Nodo Sub-Lotto (Identificato anche dal sub_lotto)
    MERGE (sub:SubLotto {doc_id: lotto.documento, id_lotto: lotto.numero_lotto, sub_lotto: lotto.sub_lotto})
    SET sub.descrizione = lotto.descrizione_completa,
        sub.misure_dettagli_tecnici = lotto.misure_dettagli,
        sub.confezionamento = lotto.confezionamento_dettagli,
        sub.importo_base_asta = lotto.importo_base_asta,
        sub.fabbisogno_totale = lotto.fabbisogno_totale
    
    // Creiamo le relazioni gerarchiche
    MERGE (doc)-[:HA_LOTTO]->(lotto_padre)
    MERGE (lotto_padre)-[:HA_SUBLOTTO]->(sub)

    // Nodi CIG (Agganciati al sub_lotto)
    FOREACH (cig_val IN lotto.codice_cig |
        MERGE (c:CIG {codice: cig_val})
        MERGE (sub)-[:HA_CIG]->(c)
    )

    // Nodi CND (Agganciati al sub_lotto)
    FOREACH (cnd_val IN lotto.codice_cnd |
        MERGE (cn:CND {codice: cnd_val})
        MERGE (sub)-[:HA_CND]->(cn)
    )

    // Nodi Strutture (Agganciati al sub_lotto)
    FOREACH (struttura IN lotto.strutture_destinatarie |
        MERGE (s:Struttura {nome: struttura})
        MERGE (s)-[:RICHIEDE_LOTTO]->(sub)
    )
"""

neo4j_query_criteria = """
    UNWIND $batch AS lotto
    
    // MATCH sul Sub-Lotto specifico, non sul padre
    MATCH (sub:SubLotto {doc_id: lotto.documento, id_lotto: lotto.numero_lotto, sub_lotto: lotto.sub_lotto})
    
    UNWIND lotto.criteri_associati AS criterio
    
    // Crea o trova il nodo Criterio universale
    MERGE (cr:Criterio {parametro: criterio.parametro})
    
    // Crea la relazione tra il Sub-Lotto e il Criterio
    MERGE (sub)-[rel:SI_VALUTA_CON]->(cr)
    
    // Salva il punteggio e la modalità SULLA RELAZIONE
    SET rel.punteggio_massimo = criterio.punteggio_massimo,
        rel.modalita_attribuzione = criterio.modalita_attribuzione
"""


# Questi sono i vincoli da creare una volta su Neo4j, per garantire l'unicità dei nodi e migliorare le performance delle query: 
# Le query saranno più veloci perché Neo4j utilizzerà gli indici sui campi unici per trovare i nodi più rapidamente, invece di dover scansionare l'intero grafo. 
# Inoltre, garantiscono l'integrità dei dati, evitando la creazione di nodi duplicati che rappresentano la stessa entità (es. due nodi DocumentoGara con lo stesso id).
# CREATE CONSTRAINT FOR (d:DocumentoGara) REQUIRE d.id IS UNIQUE;
# CREATE CONSTRAINT FOR (l:Lotto) REQUIRE (l.doc_id, l.numero) IS UNIQUE;
# CREATE CONSTRAINT FOR (c:CIG) REQUIRE c.codice IS UNIQUE;
# CREATE CONSTRAINT FOR (cn:CND) REQUIRE cn.codice IS UNIQUE;