schema = '''
    Entities:
    LOTTO {id_lotto: STRING, id_sub_lotto: STRING, codici_interni: STRING, descrizione: STRING, fabbisogno: INTEGER, importo: FLOAT, prestazioni_correlate: STRING}
    CIG {cig: STRING, durata: INTEGER}
    CND {cnd: STRING}
    CRITERIO_PREMIALE {parametro: STRING, tipologia: STRING, punteggio_massimo: FLOAT, criterio_motivazionale: STRING}

    Relationships:
    (:CIG)-[:ha_lotto]->(:LOTTO)
    (:LOTTO)-[:gara_di_riferimento]->(:CIG)
    (:LOTTO)-[:ha_sub_lotto]->(:LOTTO)
    (:LOTTO)-[:ha_CND]->(:CND)
    (:LOTTO)-[:ha_criterio_premiale]->(:CRITERIO_PREMIALE)
'''