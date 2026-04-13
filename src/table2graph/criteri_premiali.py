import pickle
import pandas as pd
import src.utils.utils as utils
from src.table2graph.query import create_query, match_query
from itertools import product
import os
import logging
from termcolor import colored
import re

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
pd.set_option('future.no_silent_downcasting', True)

path = 'data/'
main_entity = 'LOTTO'
cig = '88444520AF'

def call_create_nodes(name: string, df: DataFrame, columns: List, cig=None):

    for idx, row in df.iterrows():
        parameters = utils.format_parameters(columns, row)
        #name = df.columns[0]
        node = f'''{name}_{idx}''' #trovare modo automatico per definire label
        create_query(node, name, parameters, cig)

def crea_nodi(df: DataFrame):
    lotti = df['LOTTO'].unique()
    for l in lotti:
        logger.info(colored(f'LOTTO {l}', 'yellow'))
        lotto_slice = df.loc[df['LOTTO']==l]
        #if lotto_slice.shape[0] > 1: # vuol dire che ci sono dei sublotti
        #    #logger.info(colored('Ci sono {} sub-lotti'.format(lotto_slice.shape[0]), 'yellow'))
        #    call_create_nodes(main_entity, lotto_slice.loc[lotto_slice[mappa['IMPORTO']] != ''], [mappa['LOTTO'], mappa['IMPORTO']], 00)
            #call_create_nodes('SUB_LOTTO', lotto_slice, sublotto_header, None)
        #    for idx, row in lotto_slice.iterrows():
        #        match_query(main_entity, 'lotto', row['LOTTO'], 'SUB_LOTTO', 'sub_lotto', row['SUB_LOTTO'], 'ha_sub_lotto')
        #else:
        call_create_nodes(main_entity, lotto_slice, lotto_slice.columns, cig)

def make_header_first_row(tables, columns: List, table: DataFrame):
    x = {}
    for h, c in zip(tables["Table"][t]["header"], columns): # prima riga potrebbe non essere header ma già la prima riga di dati, da verificare
        x[c] = [h]
    print(x)
    new_df = pd.DataFrame(x)
    table = pd.concat([new_df, table], ignore_index=True)
    return table

def prepare_table_custom(tables, t: int, columns: List, new_header=True):
    logger.info(colored('Tabella #{}'.format(t), 'yellow')) 
    table = pd.DataFrame(columns=columns, data=tables['Table'][t]['rows'])
    if 'LOTTO' not in columns:
        logger.warning(colored('La colonna LOTTO non è presente nelle colonne selezionate.', 'red'))
        table.insert(0, 'LOTTO', pd.NA)
    if new_header:
        table = make_header_first_row(tables, columns, table)
    return table

def expand_dataframe(table: DataFrame, lotti: List):

    new_rows = []
    for l in lotti:
        for idx, row in table.iterrows():
                new_row = row.copy()
                new_row['LOTTO'] = l
                new_rows.append(new_row)
    d = pd.DataFrame(new_rows, columns=table.columns)

    return d

if __name__ == "__main__":

    file = 'FVG_capitolato_da_pag_77'
    utils.md2tables(file)
    tables = utils.deserialize(os.path.join('data/tables/', file+'.tab'))

    n = len(tables['Table'])
    print(n)
    dataframes = []
    #lotti_nodes = {}
    for t in range(n):
        print(tables["Table"][t]["rows"][0])
        columns = input(f'Inserisci {len(tables["Table"][t]["rows"][0])} colonne che vuoi trasformare in nodi separate da virgola: ').split(',')
        if 'skip' in columns:
            logger.info(colored('Tabella saltata', 'yellow'))
            continue
        else:
            columns = [c.strip().upper() for c in columns]
            if 'LOTTO' not in columns:
                logger.warning(colored('La colonna LOTTO non è presente nelle colonne selezionate.', 'red'))
                continue
            tmp_table = prepare_table_custom(tables, t, columns)

            lotti = tmp_table['LOTTO'].unique()
            for l in lotti:
                matches = re.findall(r'-?\d*\.?\d+', l)
                res = [float(x) if '.' in x else int(x) for x in matches]
                x = [i for i in range(res[0], res[1]+1)] 
                print(x)

            dataframes.append(expand_dataframe(tmp_table, x))
    table = pd.concat(dataframes, ignore_index = True)
    #print(table[['LOTTO', 'CRITERIO', 'TIPO', 'MAX']].drop_duplicates())
    # crea nodi lotto
    #call_create_nodes(main_entity, table[['LOTTO', 'ITEM']].drop_duplicates(), ['LOTTO', 'ITEM'], cig)
    # crea nodi criterio premiale
    #call_create_nodes('CRITERIO', table[['CRITERIO', 'TIPO', 'MAX']].drop_duplicates(), ['CRITERIO', 'TIPO', 'MAX'], None)
    #for idx, row in table.iterrows():
    #    match_query('LOTTO', 'lotto', row['LOTTO'], 'CRITERIO', 'criterio', row['CRITERIO'].replace('\'', ' '), 'ha_criterio')

