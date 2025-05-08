# agents/prompts.py
from langchain.prompts import PromptTemplate

CONSUMER_PROMPT = PromptTemplate(
    input_variables=["data_summary"],
    template="""
You are an energy consumer agent that analyzes consumption history and decides
when to place an energy order. Based on the data summary below, identify the next
2 best time windows (date and hour range) when the consumer is likely to need more energy.

Summary:
{data_summary}

Respond in the format:
{{"recommended_orders": ["YYYY-MM-DD HH:MM-HH:MM", ...]}}
"""
)

PROSUMER_PROMPT = PromptTemplate(
    input_variables=["data_summary"],
    template="""
You are a prosumer agent with rooftop generation. Your goal is to decide when to export
green energy back to the grid. Based on the generation data summary below, identify the best
2 time windows (date and hour range) when surplus energy is available.

Summary:
{data_summary}

Respond in the format:
{{"recommended_exports": ["YYYY-MM-DD HH:MM-HH:MM", ...]}}
"""
)
