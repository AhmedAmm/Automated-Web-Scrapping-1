import json
import re
from iterative_rag import systematic_rag_query
from json_repair import repair_json  # pip install json-repair

def structured_prompt_to_rag_answer(prompt_text, rag_system, llm_instance):
    """
    Turns a high-level structured prompt into multiple RAG queries,
    retrieves relevant facts, and produces a strict JSON output.
    """

    # STEP 1: Extract sub-queries from the high-level prompt
    extraction_prompt = f"""
    You are an expert in breaking down high-level requests into specific 
    factual queries for a Retrieval-Augmented Generation system.

    Prompt:
    {prompt_text}

    Identify each discrete piece of information that needs to be retrieved from the knowledge base.
    Output them as a numbered list of short, clear queries.
    Example:
    1. Competitors of Tesla in EV market
    2. Tesla Model S pricing models
    3. Recent news about Tesla
    ...
    """
    sub_queries_text = llm_instance.ask_gemini(extraction_prompt)
    sub_queries = [
        re.sub(r'^\d+\.\s*', '', q.strip())
        for q in sub_queries_text.split("\n")
        if q.strip()
    ]

    # STEP 2: Retrieve facts for each sub-query
    all_results = {}
    for sq in sub_queries:
        rag_res = systematic_rag_query(
            user_question=sq,
            rag_system=rag_system,
            llm_instance=llm_instance,
            output_format_prompt=None,
            max_iterations=1
        )
        all_results[sq] = rag_res['steps']['step3_facts']

    # STEP 3: Build final structured JSON matching the original request
    formatting_prompt = f"""
    You are to return a JSON object that matches exactly the structure described below:

    {prompt_text}

    Fill it only with the factual information below:
    {json.dumps(all_results, indent=2)}

    STRICT RULES:
    - Return VALID JSON that can be parsed by Python's json.loads without errors.
    - No trailing commas.
    - No duplicate keys.
    - Close all brackets and braces properly.
    - If a field is missing data, set it to null or [].
    - Output ONLY the JSON, no explanations or extra text.
    """

    final_json_str = llm_instance.ask_gemini(formatting_prompt).strip()

    # STEP 4: Try parsing JSON, repair if needed
    try:
        final_json = json.loads(final_json_str)
    except json.JSONDecodeError:
        try:
            repaired = repair_json(final_json_str)
            final_json = json.loads(repaired)
        except Exception as e:
            raise ValueError(
                "Generated JSON is invalid and could not be repaired:\n"
                + final_json_str
            ) from e

    return final_json
