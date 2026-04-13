import pickle
from termcolor import colored
import logging
from mrkdwn_analysis import MarkdownAnalyzer
from docling.document_converter import DocumentConverter
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
import os

# setup logger config
logger = logging.getLogger("neo4j_graphrag")
logging.basicConfig(format="%(asctime)s - %(message)s")
logger.setLevel(logging.DEBUG)

path = 'data/'

def deserialize(file):
    f = open(file, 'rb')
    obj = pickle.load(f)
    return obj

def serialize(file, item):
    pkl = open(file, 'wb')
    pickle.dump(item, pkl)
    pkl.close
    logger.info(colored('Object serialized at {}'.format(file), 'green'))

def pdf2md(file):
    # DA PDF A MD
    # da source possiamo prendere il nome del documento
    source = os.path.join(path, 'pdf', 'criteri', file+'.pdf')  # document per local path or URL
    converter = DocumentConverter()
    result = converter.convert(source).document
    result.export_to_markdown()  # output: "## Docling Technical Report[...]"
    serializer = MarkdownDocSerializer(doc=result)
    ser_result = serializer.serialize()
    ser_text = ser_result.text
    serialize(os.path.join(path, 'md', file+'.md'), ser_text)

def md2tables(file):
    # INDIVIDUA TABELLE IN MD
    analyzer = MarkdownAnalyzer(os.path.join(path, 'md', file+'.md'))
    tables = analyzer.identify_tables()
    serialize(os.path.join(path, 'tables', file+'.tab'), tables)

    return tables

def format_parameters(header, row):

    parameters = {'props': {}}
    for h in header:
        parameters["props"][h.lower()] = str(row[h]).replace('\'', ' ')
    return parameters