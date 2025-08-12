from rag1 import RAGSystem
from Llm import llm
import re

def systematic_rag_query(user_question, rag_system, llm_instance, output_format_prompt=None):
    """
    Process a user question using a simplified 3-step RAG approach for faster execution.
    
    Args:
        user_question (str): The original user question
        rag_system: Instance of RAGSystem
        llm_instance: Instance of LLM with ask_gemini method
        output_format_prompt (str): Optional prompt to guide the format/style of the final output
    
    Returns:
        dict: Complete analysis including all steps and final answer
    """
    
    def clean_response(text):
        """Clean LLM response by removing markdown and extra formatting"""
        text = re.sub(r'```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'```', '', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()
    
    # Initialize results dictionary
    results = {
        'original_question': user_question,
        'steps': {}
    }
    
    print(f"[INITIAL INPUT]\nQuestion: {user_question}")
    print("=" * 50)
    
    # COMBINED STEP 1: Reformulate and retrieve directly
    step1_prompt = f"""
    Rewrite this question to make it more suitable for document retrieval: "{user_question}"
    
    Provide only the rewritten question.
    """
    
    rewritten_question = clean_response(llm_instance.ask_gemini(step1_prompt))
    results['steps']['step1_rewritten_question'] = rewritten_question
    
    print(f"[STEP 1] Reformulated Question: {rewritten_question}")
    print("-" * 50)
    
    # STEP 2: Single RAG retrieval and fact extraction
    rag_prompt = f"""
    Provide relevant information to answer: {rewritten_question}
    
    Extract 3-5 key facts in bullet points starting with "- ".
    Focus on factual details, numbers, dates, concepts.
    If no relevant information, say "- No relevant information found"
    """
    
    try:
        rag_response = rag_system.ask(rag_prompt, rewritten_question)
        
        if isinstance(rag_response, dict):
            answer_text = rag_response.get('answer', '')
            if rag_response.get('error'):
                answer_text = "- No relevant information found due to error."
        else:
            answer_text = str(rag_response)
        
        answer_text = clean_response(answer_text)
        
        # Extract facts
        facts = []
        for line in answer_text.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                facts.append(line if line.startswith('-') else f"- {line[1:].strip()}")
            elif line and len(line) > 20:
                facts.append(f"- {line}")
        
        if not facts:
            facts = ["- No relevant information found"]
        
        has_meaningful_facts = any(not any(phrase in fact.lower() for phrase in 
            ["no information", "not available", "no relevant"]) for fact in facts)
        
        results['steps']['step2_facts'] = facts
        
        print("[STEP 2] Retrieved Facts:")
        for fact in facts:
            print(f"  {fact}")
        print("-" * 50)
    
    except Exception as e:
        facts = [f"- Error retrieving information: {str(e)}"]
        has_meaningful_facts = False
        results['steps']['step2_facts'] = facts
        print("[STEP 2] Retrieved Facts:")
        print(f"  {facts[0]}")
        print("-" * 50)
    
    # STEP 3: Generate final answer
    facts_text = "\n".join(facts)
    
    if has_meaningful_facts:
        base_step3_prompt = f"""
        Using these facts:
        {facts_text}
        
        Provide a comprehensive answer to: "{user_question}"
        
        Be concise, structured, and acknowledge limitations.
        """
    else:
        base_step3_prompt = f"""
        The knowledge base has limited information for: "{user_question}"
        
        Using available facts (if any):
        {facts_text}
        
        Provide a professional response acknowledging limitations and what additional info is needed.
        """
    
    if output_format_prompt:
        step3_prompt = base_step3_prompt + f"\n\nFollow this output format:\n{output_format_prompt}"
    else:
        step3_prompt = base_step3_prompt
    
    final_answer = clean_response(llm_instance.ask_gemini(step3_prompt))
    results['steps']['step3_final_answer'] = final_answer
    results['answer'] = final_answer
    
    print("[STEP 3] Final Answer:")
    print(final_answer)
    print("=" * 50)
    
    return results