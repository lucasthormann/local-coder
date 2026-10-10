# Local Coder
* A multi-agent system that researches and codes a concept that is provided by the user. Everything runs locally.

## Target Environment:
* A modern PC (x86_64) running a Debian-like instance

## Dependencies
* You need Ollama installed on your system
```
curl -fsSL https://ollama.com/install.sh | sh
```
* Install the necessary models
```
ollama pull llama3.1:8b
ollama pull ornith:9b
ollama pull mistral:7b
ollama pull dolphin3:8b
```
* You also need a Tavily API key
```
https://www.tavily.com/
```
### How To Run
* Clone the repo
```
git clone https://github.com/lucasthormann/local-coder.git
```
* Use a package manager to install dependencies
```
uv init
source .venv/bin/activate
uv add -r requirements.txt
```
* Create a .env file & past in your API key using the following format
```
TAVILY_API_KEY="your_tavily_api_key"
```
* Run the StreamLit app locally
```
streamlit run coder.py
```

## Run using Docker Compose
* Create a .env file & past in your API key using the following format
```
TAVILY_API_KEY="your_tavily_api_key"
```
* Start both containers
```
docker compose up --build -d
```
* Download each model into Ollama once
```
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull ornith:9b
docker compose exec ollama ollama pull mistral:7b
docker compose exec ollama ollama pull dolphin3:8b
```
* Now access the app at the following link & refresh the page
```
http://localhost:8501
```

#### Additional Information
* The system begins building a GUI in Python by default. In order to generate different code you must alter the source file.
* Most importantly, the system uses locally installed LLMs and will not function if you do not have the appropriate models downloaded.
