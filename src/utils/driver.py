import logging
import os
import dotenv
import neo4j
from termcolor import colored
from langchain_openai import AzureOpenAIEmbeddings
from schema import schema

# setup logger config
logger = logging.getLogger("neo4j_graphrag")
logging.basicConfig(format="%(asctime)s - %(message)s")
logger.setLevel(logging.DEBUG)

class N4JDriver:
    def __init__(self, URI, AUTH, embedder=None, schema=None):
        self.URI = URI
        self.AUTH = AUTH
        self.driver = neo4j.GraphDatabase.driver(URI, auth=AUTH)
        #self.dimensions = embedder.dimensions # vector embedding dimension: 256, 768, 1536, or 3072
        #self.embedder = embedder
        #self.schema = schema
        try:
            self.driver.verify_connectivity()
            logger.info(colored("Connection established!", 'green'))
        except Exception or DriverError as e:
            raise e
            
def load_environment():
    load_status = dotenv.load_dotenv(".env/neo4j.env")
    if load_status is False:
        raise RuntimeError(colored('Environment variables not loaded.', 'red'))

def initialize_driver():
    load_environment()
    embedder = AzureOpenAIEmbeddings(model=os.getenv('EMBEDDING_MODEL_NAME'), api_key=os.getenv('OPENAI_API_KEY'), api_version=os.getenv('OPENAI_API_VERSION'), azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'), dimensions=1536)
    driver = N4JDriver(URI=os.getenv('NEO4J_URI'), AUTH=(os.getenv('NEO4J_USERNAME'), os.getenv('NEO4J_PASSWORD')), embedder=embedder, schema=schema)

    return driver

if __name__ == '__main__':

    load_environment()
    #driver = N4JDriver(URI=os.getenv('NEO4J_URI'), AUTH=(os.getenv('NEO4J_USERNAME'), os.getenv('NEO4J_PASSWORD')))
    #driver = N4JDriver(URI=os.getenv('NEO4J_URI'), AUTH=(os.getenv('NEO4J_USERNAME'), os.getenv('NEO4J_PASSWORD')), 
    #    embedder=AzureOpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL_NAME"), api_key=os.getenv("OPENAI_API_KEY"), api_version=os.getenv("OPENAI_API_VERSION"), 
    #        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"), retry_min_seconds=30, retry_max_seconds=60, show_progress_bar=True, dimensions=os.getenv("EMBEDDER_DIMENSIONS"))
    #    schema=schema)