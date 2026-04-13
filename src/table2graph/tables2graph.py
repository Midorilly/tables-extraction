import pickle
import pandas as pd
import src.utils.utils as utils
from src.table2graph.query import create_query, match_query
from itertools import product
import os
import logging
from termcolor import colored

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
pd.set_option('future.no_silent_downcasting', True)

path = 'data/'

# node explosion: si parte da un nodo singolo con tutte le proprietà (e.g. nodo Lotto). Si fa un confronto tra nodi e si vede se ci sono proprietà ricorrenti tra nodi
# (e.g. CND, classe): se sì, queste proprietà diventano nodi e vengono rimosse dal nodo di partenza
# in questo modo dovrebbe essere generalizzabile per qualsiasi campo di tabelle: il nome della relazione deriva dalla proprietà stessa (CND diventa ha_CND)
# normalizzazione tabelle? identificare chi diventa nodo normalizzando la tabella
# grafo base: gara -> documento -> lotti
# grafo più raffinato: gara -> documento -> lotti -> ...

def list2string(l):
    delimiter = ",  " # Define a delimiter
    join_str = delimiter.join(l)
    return join_str

def analyse_df(header, df):

    occurrences = {}
    for h in header:
        if h != 'Contenuto':
            o = df[h].nunique()
            print(o)
            occurrences[h] = o

    print(occurrences)
    return occurrences

def find_unique_columns(c, t: DataFrame, header):
    
    # d = dizionario di colonne che hanno numero di valori unici inferiore a numero di righe totale
    d = {} 
    for h in header:
        if t[h].nunique() < t.shape[0]:
            d[h] = t[h].nunique()    
    lotti = []        
    for k in d.keys():
        if 'LOTTO' in k:
            lotti.append(k)
    for l in lotti:
        del d[l]
    logger.info('Colonne che hanno numero di valori unici inferiore a numero di righe totale')
    print(d)

    l = {}
    temp_d = d.copy()
    for k, v in d.items():
        columns = (k,) # inizio con colonna singola k
        del temp_d[k] # rimuovo la colonna dalla copia di d
        for temp_k, temp_v in temp_d.items(): # itero su copia di d
            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            if temp_k != k and temp_v == v: # verifico che v e temp_v siano uguali 
            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                new_columns = columns + (temp_k,) # concateno colonna iniziale a colonna temp_k
                df = pd.DataFrame(data=t[list(new_columns)]) # creo un df solo di quelle due colonne
                df['nunique?'] = df[df.columns[0:]].apply(      # merge delle colonne x verificare se una volta unite il numero di valori unici è ancora lo stesso
                    lambda x: ' '.join(x.dropna().astype(str)),
                    axis=1
                )
                print(df)
                df_v = df['nunique?'].nunique()
                if df_v == v: # se numero di valori unici è ancora == v
                    temp_tuple = (new_columns, v) # aggiorno temp_tuple con la nuova tupla di colonne e v
                    print(temp_tuple)
                    print(f'{temp_tuple} are compatible!')
                else:
                    temp_tuple = (columns, v)
                    print(f'{new_columns} are not compatible! {df_v}, {v}')
                l[temp_tuple[0]] = temp_tuple[1] # salva la tupla calcolata al ciclo precednte ma se non l'ho ancora calcolata?
            else:
                l[temp_k] = temp_v

    logger.info(colored('COLONNE SINGOLE', 'yellow'))
    #print(l)
    '''new_nodes = {}
    if len(l.keys())>1:
        for k1, v1 in l.items():
            for k2, v2 in l.items():
                if v1 == v2 and k1 != k2:
                    if set(k1).issubset(k2):
                        new_nodes[k2] = v2
                    elif set(k2).issubset(k1):
                        new_nodes[k1] = v1
                else:
                    new_nodes[k1] = v1
                    new_nodes[k2] = v2             
    else:'''
    new_nodes = l

    #print('NEW NODES')
    #print(new_nodes)
    return d


def call_create_nodes(name: string, df: DataFrame, columns: List, cig=None):

    for idx, row in df.iterrows():
        parameters = format_parameters(columns, row)
        #name = df.columns[0]
        node = f'''{name}_{idx}''' #trovare modo automatico per definire label
        create_query(node, name, parameters, cig)

def call_match_query(df: DataFrame, object_entity):
    for idx, row in df.iterrows():
        match_query(main_entity, 'lotto', row['LOTTO'], object_entity, object_entity.lower(), row[object_entity], 'ha_'+object_entity)

def create_nodes(df: DataFrame, cols, cig: str):
    all_columns = []
    for c in cols:
        all_columns = all_columns + c
    print(all_columns)
    dataframe = df.copy().drop(columns=all_columns)
    dataframe = dataframe.drop_duplicates()
    # creo grafo lotto da df principale dopo aver tolto le sottotabelle individuate
    call_create_nodes(dataframe, cig)

    for c in cols:
        logger.info(colored(c, 'yellow'))
        sliced_df = df[c].copy().drop_duplicates()
        call_create_nodes(sliced_df, None)

def rename_header(header):
    renaming = {}
    for h in header:
        renaming[h] = h.upper().replace(' ', '_').replace('.', '').replace('(', '').replace(')', '') 
    return renaming

def cig_node(cig):
    logger.info(colored(f'CIG {cig}', 'yellow'))
    parameters = {'props': {}}
    parameters['props']['cig'] = cig
    create_query('CIG'+cig, 'CIG', parameters, None)

def clean_cnd(df: DataFrame, column):

    i = df.columns.get_loc(column)

    for idx, row in df.iterrows():
        x = row[column]
        y = x.split(' ')[-1]
        df.at[idx, column] = y
    return df       

def prepare_table(tables, t: int):
    logger.info(colored('Tabella #{}'.format(t), 'yellow')) 
    df = pd.DataFrame(columns=tables['Table'][t]['header'], data=tables['Table'][t]['rows'])
    #print(df)
    renaming = rename_header(tables['Table'][t]['header'])
    renamed_table = df.rename(columns=renaming)
    clean_table = renamed_table.loc[df['LOTTO'] != '']
    #header = list(clean_table)
    #logger.info(header)
    table = clean_cnd(clean_table.copy(), 'CND')

    return table

# crea nodi lotto e sub lotto
def nodi_lotto(df: DataFrame, cig: str):
    table = df.copy().drop(taxonomy_entities, axis=1)
    lotti = table['LOTTO'].unique()
    sublotto_header = ['SUB_LOTTO', 'COD_INTERNI', 'DESCRIZIONE_LOTTO', 'PRESTAZIONI_CORRELATE', 'FABBISOGNO_CVO_36_MESI']
    for l in lotti:
        logger.info(colored(f'LOTTO {l}', 'yellow'))
        lotto_slice = table.loc[table['LOTTO']==l]
        if lotto_slice.shape[0] > 1: # vuol dire che ci sono dei sublotti
            logger.info(colored('Ci sono {} sub-lotti'.format(lotto_slice.shape[0]), 'yellow'))
            call_create_nodes(main_entity, lotto_slice.loc[lotto_slice[mappa['IMPORTO']] != ''], [mappa['LOTTO'], mappa['IMPORTO']], cig)
            call_create_nodes('SUB_LOTTO', lotto_slice, sublotto_header, None)
            for idx, row in lotto_slice.iterrows():
                match_query(main_entity, 'lotto', row['LOTTO'], 'SUB_LOTTO', 'sub_lotto', row['SUB_LOTTO'], 'ha_sub_lotto')
        else:
            call_create_nodes(main_entity, lotto_slice, lotto_slice.columns, cig)

def nodi_tassonomie(df: Dataframe):
    for tax in taxonomy_entities:
        call_create_nodes(tax, df.drop_duplicates([tax]), [tax], None)
        call_match_query(df, tax)

def tabella_lotti(path):

    for doc in os.listdir(os.path.join(path, 'pdf')):
        # recupero cig e creo nodo
        cig = doc.split('_')[1].split('.')[0]
        cig_node(cig)
        # pdf to markdown + identificare tabelle nel doc
        file = doc.split('.')[0]
        pdf2md(file)
        tables = md2tables(file)
        tables = utils.deserialize(os.path.join('data/tables/', file+'.tab'))

        n = len(tables['Table'])
        dataframes = []
        for t in range(n):
            tmp_table = prepare_table(tables, t)
            dataframes.append(tmp_table)
        table = pd.concat(dataframes, ignore_index = True).drop_duplicates()
        header = list(table)
        print(table)

        nodi_lotto(table, cig)
        nodi_tassonomie(table)


# campi fissi
# LOTTO (SUB-LOTTO) FABBISONO IMPORTO
# supponiamo di avere una chiamata a llm che restituisce mappatura

mappa = {'LOTTO' : 'LOTTO',
    'SUB_LOTTO' : 'SUB_LOTTO',
    'FABBISOGNO' : 'FABBISOGNO_CVO_36_MESI',
    'IMPORTO' : 'IMPORTO_36_MESI'
}

main_entity = 'LOTTO'
taxonomy_entities = ['CND']

if __name__ == '__main__':
    
    #tabella_lotti(path)
    file = 'Allegato_8_Criteri_Abruzzo'
    tables = utils.deserialize(os.path.join('data/tables/', file+'.tab'))
    #utils.pdf2md(file)
    #tables = utils.md2tables(file)
    #print(tables)
    
    n = len(tables['Table'])
    print(n)
    dataframes = []
    for t in range(n):
        print(tables["Table"][t]["rows"][0])
        columns = input(f'Inserisci {len(tables["Table"][t]["rows"][0])} colonne che vuoi trasformare in nodi separate da virgola: ').split(',')
        columns = [c.strip().upper() for c in columns]
        tmp_table = prepare_table_custom(tables, t, columns)
        #dataframes.append(tmp_table)
        crea_nodi(tmp_table)
    #table = pd.concat(dataframes, ignore_index = True).drop_duplicates()
    #header = list(table)
    #print(table)

