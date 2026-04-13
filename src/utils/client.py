from openai import OpenAI, AzureOpenAI
from together import Together
import driver 
import os

driver.load_environment()

instruction = f''''''

def query_client(user, model, client):

    if model == os.getenv('GPT_5_MODEL_NAME') or model == os.getenv('GPT_4O_MINI_MODEL_NAME') or model == os.getenv('GPT_O4_MINI_MODEL_NAME'):
        completion = client.chat.completions.create(
            messages=[
                { "role": "system", "content": instruction},
                { "role": "user", "content": user}
            ],
            max_completion_tokens=4096,
            model=model
        )
        answer = completion.choices[0].message.content

    elif model == os.getenv('LLAMA_70B_MODEL_NAME'): # or model == os.getenv('LLAMA_8B_MODEL_NAME'):
        completion = client.chat.completions.create(
            model = model,
            messages= [
                { "role": "system", "content": instruction},
                { "role": "user", "content": user}
            ],
        )
        answer = completion.choices[0].message.content

    elif model == os.getenv('LLAMA_8B_MODEL_NAME'):
        completion = client.chat.completions.create(
            model = 'meta-llama/'+model,
            messages= [
                { "role": "system", "content": instruction},
                { "role": "user", "content": user}
            ],
        )
        answer = completion.choices[0].message.content
    
    return answer

def client_setup(model): 

    if model == os.getenv('GPT_5_MODEL_NAME') or model == os.getenv('GPT_4O_MINI_MODEL_NAME') or model == os.getenv('GPT_O4_MINI_MODEL_NAME'):
        client = AzureOpenAI(
            api_version=os.getenv("OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout= 500.0 #180.0
        )
        #deployment = os.getenv("AZURE_DEPLOYMENT")

    elif model == os.getenv('LLAMA_70B_MODEL_NAME'): #or model == os.getenv('LLAMA_8B_MODEL_NAME'):
        client = OpenAI(
            base_url=os.getenv("LLAMA_ENDPOINT"), #cambia base url x together ai
            api_key=os.getenv("LLAMA_API_KEY"),
        )
    
    elif model == os.getenv('LLAMA_8B_MODEL_NAME'):
        client = Together()

    return client
