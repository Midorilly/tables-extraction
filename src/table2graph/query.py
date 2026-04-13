import neo4j
from src.utils.driver import N4JDriver, load_environment
import logging
import os

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_environment()
driver = N4JDriver(URI=os.getenv('NEO4J_URI'), AUTH=(os.getenv('NEO4J_USERNAME'), os.getenv('NEO4J_PASSWORD')))

def create_query(name: str, t: str, parameters, cig=None):
    query = '''CREATE ({}:{} $props)'''.format(name, t)
    if cig:
        query = '''MATCH (n:CIG) WHERE n.cig = '{}' '''.format(cig) + query + '''<-[:ha_lotto]-(n)''' 
    print(query)
    insertion = driver.driver.execute_query(query, parameters_=parameters).summary

def match_query(n_class, n_param, n_value, m_class, m_param, m_value, rel):

    query = '''MATCH (n:{}) WHERE n.{} = '{}'
               MATCH (m:{}) WHERE m.{} = '{}' 
               MERGE (n)-[:{}]->(m) 
               RETURN *'''.format(n_class, n_param, n_value, m_class, m_param, m_value, rel)
    print(query)
    insertion = driver.driver.execute_query(query).summary