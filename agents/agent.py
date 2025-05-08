from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from langchain_openai import OpenAI
from langchain.prompts import PromptTemplate
from agents.prompts import CONSUMER_PROMPT, PROSUMER_PROMPT
from utils.csv_loader import load_csv_summary
import os

class EnergyAgent:
    def __init__(self, role: str, data_path: str):
        if role not in ["consumer", "prosumer"]:
            raise ValueError("Role must be either 'consumer' or 'prosumer'")
        self.role = role
        self.data_path = data_path
        # self.llm = OpenAI(temperature=0.3)
        self.llm = OpenAI(temperature=0.3, openai_api_key=os.getenv("OPENAI_API_KEY"))

    def decide_energy_action(self):
        summary = load_csv_summary(self.data_path)
        prompt = CONSUMER_PROMPT if self.role == "consumer" else PROSUMER_PROMPT

        chain = prompt | self.llm
        result = chain.invoke({"data_summary": summary})
        return result