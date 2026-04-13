import logging
import os
import dotenv
import neo4j
from langchain_openai import OpenAIEmbeddings
from neo4j_graphrag.indexes import create_vector_index, upsert_vectors, drop_index_if_exists
from random import random
from langchain_community.vectorstores import Neo4jVector
import src.utils.driver as driver
from termcolor import colored
import re

# setup logger config
logger = logging.getLogger("neo4j_graphrag")
logging.basicConfig(format="%(asctime)s - %(message)s")
logger.setLevel(logging.DEBUG)

labels =  ['CIG', 'LOTTO', 'SUB_LOTTO', 'CND']
to_skip = []

def get_node_properties(neo4jdriver, label, id):

    records, _, _ = neo4jdriver.driver.execute_query(
        f'''
            MATCH (n:{label}) WHERE elementId(n) = '{id}'
            RETURN keys(n) AS properties LIMIT 1
        '''
    )

    properties = records[0].data()['properties']

    return properties

def create_embeddings(neo4jdriver):

    for label in labels:
        logger.info(colored(f'LABEL {label}', 'yellow'))
        records, _, _ = neo4jdriver.driver.execute_query(
        f'''
            MATCH (n:{label})
            RETURN n, elementId(n) as id
        '''
        )

        for record in records:
            text = ''
            id = record.data()['id']
            properties = get_node_properties(neo4jdriver, label, id)
            for prop in properties:
                if prop not in to_skip:
                    if isinstance(record.data()['n'][prop], list):
                        val = ', '.join([str(v) for v in record.data()['n'][prop]])
                    else:
                        val = record.data()['n'][prop]
                    val = re.sub('\'', ' ', val)
                    prop = re.sub('_', ' ', prop)
                    text = text + f'{prop}: {val}\n'
            
            query = f'''
                MATCH (n) WHERE elementId(n) = '{id}'
                SET n._text = '{text}'
            '''
            _, _, _ = neo4jdriver.driver.execute_query(query)

def create_index(driver: N4JDriver, index: str, label: str, embedding_node_property: str):

    logger.info(f'Creating index for {label}')

    create_vector_index(
        driver.driver,
        index,
        label=label, # node label to be indexed
        embedding_property=embedding_node_property, # property key of a node which contains embedding values
        dimensions=driver.dimensions, 
        similarity_fn="cosine", # vector similarity function: euclidean or cosine
    )

def properties_embedding(label: str, properties: list, index: str, driver: N4JDriver, embedding_node_property: str):

    logger.info(f'Embedding properties of {label}')

    embeddings = Neo4jVector.from_existing_graph(
        embedding = driver.embedder,
        url = driver.URI,
        username = driver.AUTH[0],
        password = driver.AUTH[1],
        index_name = index,
        node_label = label,
        text_node_properties = properties,
        embedding_node_property = embedding_node_property
    )

def query_neo4j(l, neo4jdriver):

    records, summary, keys = neo4jdriver.driver.execute_query(
        f"""
        MATCH (n:{l})
        RETURN keys(n) LIMIT 1
        """,
        database_='neo4j'
    )
    return records

def create_index(driver, label, embedding_node_property):

    index = label.upper()+'_INDEX'
    drop_index_if_exists(driver.driver, index)
    properties_embedding(label, ['_text'], index, driver, embedding_node_property)
    create_index(driver, index, label, embedding_node_property)      
    
if __name__ == '__main__':

    neo4jdriver = driver.initialize_driver()
    create_embeddings(driver=neo4jdriver)
    create_index(driver=neo4jdriver, label ='Embedding', embedding_node_property = '_embedding')
