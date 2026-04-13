import logging
import os
import sys
import dotenv
import neo4j
from langchain_openai import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.llm import OpenAILLM, AzureOpenAILLM
from neo4j_graphrag.retrievers import VectorCypherRetriever, VectorRetriever, Text2CypherRetriever, text2cypher
from openai import AzureOpenAI
import re
from termcolor import colored
from neo4j.exceptions import CypherSyntaxError, GqlError
from pydantic import ValidationError
from neo4j_graphrag.exceptions import SearchValidationError, Text2CypherRetrievalError
from neo4j_graphrag.generation.prompts import Text2CypherTemplate
from neo4j_graphrag.schema import get_schema
from neo4j_graphrag.types import Text2CypherSearchModel

import src.utils.driver as driver


# setup logger config
logger = logging.getLogger('neo4j_graphrag')
logging.basicConfig(format='%(asctime)s - %(message)s')
logger.setLevel(logging.DEBUG)

def preprocess(t2c_query, word='MATCH'):

    t2c_query = re.sub('\\s\\{.*?\\}', '', t2c_query)

    idx = t2c_query.find(word)
    if idx != -1:
        return t2c_query[idx:]
    else:
        return t2c_query

def write_cypher_query(t2c_retriever, neo4jdriver, nl_query, llm):

    try: 
        t2c_query = t2c_retriever.get_search_results(nl_query).metadata['cypher']
        t2c_query = preprocess(t2c_query)
        #label = prompt_GPT(nl_query, t2c_query, neo4jdriver.schema)

        #logger.info(colored(f'INDEX {index_name}', 'yellow'))

        return t2c_query

    except Text2CypherRetrievalError or CypherSyntaxError or GqlError or SearchValidationError as e:
        raise e
    
def prompt_GPT(nlQuery, cypherQuery, schema): 

    client = AzureOpenAI(
        api_version=os.getenv('OPENAI_API_VERSION'),
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
        api_key=os.getenv('OPENAI_API_KEY')
    )

    response = client.chat.completions.create(
        messages=[
            { "role": "system", "content": 'Given a natural language query, the correspondent Cypher query, and the graph schema, determine the most informative node label. Answer only with the node label.'},
            { "role": "user", "content": f'Natural language query: {nlQuery}\nCypher query: {cypherQuery}\nGraph schema: {schema}' }
        ],
        model=os.getenv('GPT_O4_MINI_MODEL_NAME')
    )

    return response.choices[0].message.content

def neo4j_graphrag(nl_query, llm, retriever):

    try:
        rag = GraphRAG(retriever=retriever, llm=llm)
        response = rag.search(query_text=nl_query, return_context=True, response_fallback='I can not answer this question because I have no relevant context.')
        return response
    except Text2CypherRetrievalError or CypherSyntaxError or GqlError or SearchValidationError as e:
        raise e

# Toy example
if __name__ == '__main__':

    neo4jdriver = driver.initialize_driver()
    #To create an index, run the following line, or directly run index.py. At the moment, an index for each node class is already available
    #index.init_index(neo4jdriver)
    retriever_type = sys.argv[1] #v for vector, vc for vectorcypher

    #nl_query = 'Quali sono i CND dei lotti che includono aghi per biopsia?'
    nl_query = 'Considera gli aghi per anestesia. Per ogni lotto restituisci i CND, la quantità, i prezzi a base d\'asta'
    #nl_query = 'Considera gli aghi per biopsia laparoscopica. Trova i prezzi a base d\'asta, indicando l\'unità di misura corrispondente al prezzo e la gara di riferimento'
    #llm = AzureOpenAI(azure model=os.getenv('GPT_4O_MINI_MODEL_NAME'), model_params={'temperature': 0})
    llm = AzureOpenAILLM(model_name=os.getenv('GPT_O4_MINI_MODEL_NAME'),
            api_version=os.getenv('OPENAI_API_VERSION'),
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
            api_key=os.getenv('OPENAI_API_KEY')
        )

    try:
        index_name = 'EMBEDDING_INDEX'

        if retriever_type == 'v':
            retriever = VectorRetriever(
                driver=neo4jdriver.driver,
                index_name=index_name,
                embedder=neo4jdriver.embedder)
        
        elif retriever_type == 'vc':
            t2c_retriever = Text2CypherRetriever(
                driver=neo4jdriver.driver,
                llm=llm,
                neo4j_schema=neo4jdriver.schema
            )
            cypher_query = write_cypher_query(t2c_retriever, neo4jdriver, nl_query, llm)
            retriever = VectorCypherRetriever(
                driver=neo4jdriver.driver,
                index_name=index_name, 
                embedder=neo4jdriver.embedder,
                retrieval_query=cypher_query)
            logger.info(colored(f'CYPHER QUERY\n{cypher_query}', 'yellow'))
        response = neo4j_graphrag(nl_query, llm, retriever)

        # Forces answer if Cypher Query does not work
        if not response.retriever_result.items:
            logger.info(colored('WARNING: incorrect Cypher query. Switching to VectorRetriever.'))
            retriever = VectorRetriever(
                driver=neo4jdriver.driver,
                index_name=index_name,
                embedder=neo4jdriver.embedder
            )
            response = neo4j_graphrag(nl_query, llm, retriever)

        logger.info(colored(response.answer, 'green'))

    except Text2CypherRetrievalError as e:
        logger.info(colored(f'Text2CypherRetrievalError: skipping question', 'red'))
    
    except CypherSyntaxError or GqlError or SearchValidationError as e:
        logger.info(colored(f'Failed to get search result: {e.message}', 'red'))

    neo4jdriver.driver.close()
    logger.info('Connection closed.')