import pandas as pd

from agents.csv_agent import create_agent, build_tools
from pipeline.data_manager import DataManager
from langchain_core.messages import HumanMessage, SystemMessage
from agents.prompts import SYSTEM_PROMPT


dm = DataManager()

dm.datasets = {
    "patients": pd.DataFrame({
        "patient_id": ["1", "2", "3"],
        "age": ["34", "67", "52"],
    }),
    "conditions": pd.DataFrame({
        "patient_id": ["1", "1", "3"],
        "condition": ["diabetes", "hypertension", "diabetes"],
    }),
}

dm.dictionary = {
    "patients": {
        "rows": 3,
        "columns": ["patient_id", "age"],
        "dtypes": {"patient_id": "object", "age": "object"},
        "descriptions": {},
    },
    "conditions": {
        "rows": 3,
        "columns": ["patient_id", "condition"],
        "dtypes": {"patient_id": "object", "condition": "object"},
        "descriptions": {},
    },
}

tools = build_tools(dm)
agent = create_agent(dm, tools=tools)

messages = [
    SystemMessage(content=SYSTEM_PROMPT),
    HumanMessage(content="Qual é a idade média dos pacientes com diabetes?")
]

response = agent.invoke(messages)

print(response)
print("TOOL CALLS:", getattr(response, "tool_calls", None))
