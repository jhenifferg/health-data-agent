# Health Data Agent

Aplicação web para carregar arquivos CSV ou ZIP, explorar metadados e consultar dados em linguagem natural com apoio de IA. O projeto combina uma API FastAPI, uma interface React e um agente que transforma perguntas em operações estruturadas sobre os dados.

## Funcionalidades

- Upload e validação de arquivos CSV e ZIP
- Detecção de encoding e normalização de colunas
- Geração de metadados e dicionário de dados
- Consultas em linguagem natural sobre um dataset
- Workspaces para consultar vários datasets em conjunto
- Operações de filtro, contagem, agregação, ordenação e valores distintos
- Suporte aos provedores Gemini e Groq
- Tratamento de limites, indisponibilidade e cooldown dos provedores
- API documentada automaticamente pelo FastAPI

## Tecnologias

**Backend:** Python, FastAPI, Pandas, Pydantic, LangChain, Gemini e Groq  
**Frontend:** React 19, Vite e Oxlint  
**Testes:** Pytest e HTTPX

## Estrutura do projeto

```text
health-data-agent/
├── agents/        # Configuração do agente e prompts
├── api/           # Aplicação, rotas e schemas FastAPI
├── frontend/      # Interface React/Vite
├── pipeline/      # Leitura, validação e preparação dos dados
├── services/      # Regras de negócio, sessões e provedores
├── tests/         # Testes automatizados
├── tools/         # Ferramentas de consulta e manipulação de CSV
├── app.py         # Entrada do backend
└── requirements.txt
```

## Pré-requisitos

- Python 3.10 ou superior
- Node.js 20 ou superior
- Uma chave de API do Google Gemini ou da Groq

## Configuração do backend

Clone o repositório e entre na pasta do projeto:

```bash
git clone https://github.com/jhenifferg/health-data-agent.git
cd health-data-agent
```

Crie e ative um ambiente virtual:

```bash
python -m venv venv
source venv/bin/activate
```

No Windows, use:

```powershell
venv\Scripts\activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz. Escolha um dos provedores:

```env
# Gemini
AI_PROVIDER=gemini
GOOGLE_API_KEY=sua_chave_aqui
GEMINI_MODEL=gemini-flash-latest

# Ou Groq
# AI_PROVIDER=groq
# GROQ_API_KEY=sua_chave_aqui
# GROQ_MODEL=openai/gpt-oss-20b
```

O arquivo `.env` está ignorado pelo Git e não deve ser publicado.

Inicie a API:

```bash
python app.py
```

A API ficará disponível em `http://127.0.0.1:8000`. A documentação interativa pode ser acessada em `http://127.0.0.1:8000/docs`.

## Configuração do frontend

Em outro terminal:

```bash
cd frontend
npm install
npm run dev
```

A interface ficará disponível em `http://localhost:5173` e se comunica com a API local na porta `8000`.

## Uso

1. Abra a interface web.
2. Envie um arquivo CSV ou um ZIP contendo arquivos CSV.
3. Confira o resumo do dataset carregado.
4. Faça perguntas em linguagem natural, por exemplo:
   - `Quantos registros existem?`
   - `Quais são os valores únicos da coluna sexo?`
   - `Qual é a média de idade por diagnóstico?`

Os arquivos processados ficam na pasta local `.runtime/`, que também está fora do controle de versão.

## Endpoints principais

| Método | Endpoint | Descrição |
| --- | --- | --- |
| `GET` | `/api/health` | Verifica o estado da API |
| `POST` | `/api/datasets` | Envia um CSV ou ZIP |
| `GET` | `/api/datasets/{dataset_id}` | Consulta metadados do dataset |
| `POST` | `/api/datasets/{dataset_id}/query` | Faz uma pergunta sobre um dataset |
| `POST` | `/api/workspaces` | Cria um workspace |
| `GET` | `/api/workspaces/{workspace_id}` | Consulta um workspace |
| `POST` | `/api/workspaces/{workspace_id}/datasets/{dataset_id}` | Adiciona um dataset |
| `DELETE` | `/api/workspaces/{workspace_id}/datasets/{dataset_id}` | Remove um dataset |
| `POST` | `/api/workspaces/{workspace_id}/query` | Consulta os datasets do workspace |

## Testes e qualidade

Execute os testes do backend:

```bash
pytest
```

No frontend, verifique o código e gere uma versão de produção com:

```bash
cd frontend
npm run lint
npm run build
```

## Segurança

- Nunca publique o arquivo `.env` ou chaves de API.
- Valide os dados antes de utilizá-los em ambientes sensíveis.
- Dados enviados são armazenados apenas no diretório de runtime local configurado para a aplicação.

## Status

Projeto em desenvolvimento.
