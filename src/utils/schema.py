neo4j_query = """
    UNWIND $batch AS lotto
    
    // Document Node
    MERGE (doc:DocumentoGara {id: lotto.documento})
    SET doc.numero_gara = lotto.numero_gara
    
    // Father Lotto Node
    MERGE (lotto_padre:Lotto {doc_id: lotto.documento, id_lotto: lotto.numero_lotto})
    SET lotto_padre.numero_gara = lotto.numero_gara,
        lotto_padre.durata_contratto_mesi = lotto.durata_contratto_mesi
    MERGE (doc)-[:HA_LOTTO]->(lotto_padre)

    // CIG Nodes (connected to Father Lotto)
    FOREACH (cig_val IN lotto.codice_cig |
        MERGE (c:CIG {codice: cig_val})
        MERGE (lotto_padre)-[:HA_CIG]->(c)
    )

    // First Case: Sublotto exists, create SubLotto Node and connect to Father Lotto
    FOREACH (_ IN CASE WHEN lotto.sub_lotto <> "" THEN [1] ELSE [] END |
        MERGE (sub:SubLotto {doc_id: lotto.documento, id_lotto: lotto.numero_lotto, sub_lotto: lotto.sub_lotto})
        SET sub.descrizione = lotto.descrizione_completa,
            sub.altri_dettagli = lotto.altri_dettagli,
            sub.misure_dettagli_tecnici = lotto.misure_dettagli,
            sub.confezionamento = lotto.confezionamento_dettagli,
            sub.importo_base_asta = lotto.importo_base_asta,
            sub.importo_totale = lotto.importo_totale,
            sub.fabbisogno_totale = lotto.fabbisogno_totale,
            sub.durata_contratto_mesi = lotto.durata_contratto_mesi
        
        MERGE (lotto_padre)-[:HA_SUBLOTTO]->(sub)

        // CND Nodes (connected to SubLotto)
        FOREACH (cnd_val IN lotto.codice_cnd |
            MERGE (cn:CND {codice: cnd_val})
            MERGE (sub)-[:HA_CND]->(cn)
        )

        // Struttura Nodes (connected to SubLotto)
        FOREACH (struttura IN lotto.strutture_destinatarie |
            MERGE (s:Struttura {nome: struttura})
            MERGE (s)-[:RICHIEDE_LOTTO]->(sub)
        )
    )

    // Second Case: Sublotto does not exist, set properties on Father Lotto and connect CND and Struttura nodes to Father Lotto
    FOREACH (_ IN CASE WHEN lotto.sub_lotto = "" THEN [1] ELSE [] END |
        SET lotto_padre.descrizione = lotto.descrizione_completa,
            lotto_padre.altri_dettagli = lotto.altri_dettagli,
            lotto_padre.misure_dettagli_tecnici = lotto.misure_dettagli,
            lotto_padre.confezionamento = lotto.confezionamento_dettagli,
            lotto_padre.importo_base_asta = lotto.importo_base_asta,
            lotto_padre.importo_totale = lotto.importo_totale,
            lotto_padre.fabbisogno_totale = lotto.fabbisogno_totale,
            lotto_padre.durata_contratto_mesi = lotto.durata_contratto_mesi

        // CND Nodes (connected to Father Lotto)
        FOREACH (cnd_val IN lotto.codice_cnd |
            MERGE (cn:CND {codice: cnd_val})
            MERGE (lotto_padre)-[:HA_CND]->(cn)
        )

        // Struttura Nodes (connected to Father Lotto)
        FOREACH (struttura IN lotto.strutture_destinatarie |
            MERGE (s:Struttura {nome: struttura})
            MERGE (s)-[:RICHIEDE_LOTTO]->(lotto_padre)
        )
    )
"""

neo4j_query_criteria = """
    UNWIND $batch AS lotto
    
    // Criteria Handling if Sublotto exists
    FOREACH (_ IN CASE WHEN lotto.sub_lotto <> "" THEN [1] ELSE [] END |
        MERGE (sub:SubLotto {doc_id: lotto.documento, id_lotto: lotto.numero_lotto, sub_lotto: lotto.sub_lotto})
        FOREACH (criterio IN lotto.criteri_associati |
            MERGE (cr:Criterio {parametro: criterio.parametro})
            MERGE (sub)-[rel:SI_VALUTA_CON]->(cr)
            SET rel.punteggio_massimo = criterio.punteggio_massimo,
                rel.modalita_attribuzione = criterio.modalita_attribuzione,
                rel.dettagli_valutazione = criterio.dettagli_valutazione
        )
    )

    // Criteria Handling if Sublotto does not exist (connect to Father Lotto)
    FOREACH (_ IN CASE WHEN lotto.sub_lotto = "" THEN [1] ELSE [] END |
        MERGE (lotto_padre:Lotto {doc_id: lotto.documento, id_lotto: lotto.numero_lotto})
        FOREACH (criterio IN lotto.criteri_associati |
            MERGE (cr:Criterio {parametro: criterio.parametro})
            MERGE (lotto_padre)-[rel:SI_VALUTA_CON]->(cr)
            SET rel.punteggio_massimo = criterio.punteggio_massimo,
                rel.modalita_attribuzione = criterio.modalita_attribuzione,
                rel.dettagli_valutazione = criterio.dettagli_valutazione
        )
    )
"""


# Questi sono i vincoli da creare una volta su Neo4j, per garantire l'unicità dei nodi e migliorare le performance delle query: 
# Le query saranno più veloci perché Neo4j utilizzerà gli indici sui campi unici per trovare i nodi più rapidamente, invece di dover scansionare l'intero grafo. 

# CREATE CONSTRAINT FOR (d:DocumentoGara) REQUIRE d.id IS UNIQUE;
# CREATE CONSTRAINT FOR (l:Lotto) REQUIRE (l.doc_id, l.id_lotto) IS UNIQUE;
# CREATE CONSTRAINT FOR (sub:SubLotto) REQUIRE (sub.doc_id, sub.id_lotto, sub.sub_lotto) IS UNIQUE;
# CREATE CONSTRAINT FOR (c:CIG) REQUIRE c.codice IS UNIQUE;
# CREATE CONSTRAINT FOR (cn:CND) REQUIRE cn.codice IS UNIQUE;
# CREATE CONSTRAINT FOR (s:Struttura) REQUIRE s.nome IS UNIQUE;
# CREATE CONSTRAINT FOR (cr:Criterio) REQUIRE cr.parametro IS UNIQUE;