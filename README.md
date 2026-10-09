# Local Coder
* A multi-agent system that researches and codes a concept that is provided by the user. Everything runs locally.

## Target Environment:
* A modern PC (x86_64) running a Debian-like instance

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
* Run the StreamLit app locally
```
streamlit run coder.py
```

#### Additional Information
* The system begins building a GUI in Python by default. In order to generate different code you must alter the source file.
* Most importantly, the system uses locally installed LLMs and will not function if you do not have the appropriate models downloaded
