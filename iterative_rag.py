from rag1 import RAGSystem
from Llm import llm
import re

def systematic_rag_query(user_question, rag_system, llm_instance, output_format_prompt=None, max_iterations=2):
    """
    Process a user question using a systematic 6-step RAG approach.
    
    Args:
        user_question (str): The original user question
        rag_system: Instance of RAGSystem
        llm_instance: Instance of LLM with ask_gemini method
        output_format_prompt (str): Optional prompt to guide the format/style of the final output
        max_iterations (int): Maximum number of refinement iterations
    
    Returns:
        dict: Complete analysis including all steps and final answer
    """
    
    def clean_response(text):
        """Clean LLM response by removing markdown and extra formatting"""
        # Remove markdown code blocks
        text = re.sub(r'```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'```', '', text)
        # Clean up extra whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()
    
    def has_meaningful_information(text):
        """Check if the text contains meaningful information or just 'no information' messages"""
        if not text or text.strip() == "":
            return False
        
        negative_phrases = [
            "no information", "not available", "cannot be found", "does not contain",
            "unable to", "no relevant documents", "cannot answer", "not possible to",
            "no specific information", "information not available", "no data"
        ]
        
        return not any(phrase in text.lower() for phrase in negative_phrases)
    
    # Initialize results dictionary
    results = {
        'original_question': user_question,
        'steps': {},
        'iterations': 0
    }
    
    print(f"[INITIAL INPUT]\nQuestion: {user_question}")
    print("=" * 50)
    
    # STEP 1: Reformulate the question
    step1_prompt = f"""
    [STEP 1] Reformulate the question for search:
    
    Original question: "{user_question}"
    
    Rewrite this question to make it more suitable for document retrieval and search. 
    Make it more specific, use better keywords, and ensure it's clear what information is needed.
    
    Provide only the rewritten question, nothing else.
    """
    
    rewritten_question = clean_response(llm_instance.ask_gemini(step1_prompt))
    results['steps']['step1_rewritten_question'] = rewritten_question
    
    print(f"[STEP 1] Reformulate the question for search:")
    print(f"Rewritten Question: {rewritten_question}")
    print("###")
    print("-" * 50)
    
    # STEP 2: Identify sub-questions
    step2_prompt = f"""
    [STEP 2] Identify sub-questions or aspects:
    
    Question: "{rewritten_question}"
    
    Break this question into 3-5 key sub-questions or information needs that cover all important aspects of the topic.
    Each sub-question should be specific and answerable.
    
    Format your response as:
    1. [Sub-question 1]
    2. [Sub-question 2]
    3. [Sub-question 3]
    etc.
    
    Provide only the numbered list of sub-questions.
    """
    
    sub_questions_response = clean_response(llm_instance.ask_gemini(step2_prompt))
    # Parse sub-questions
    sub_questions = []
    for line in sub_questions_response.split('\n'):
        if re.match(r'^\d+\.', line.strip()):
            sub_questions.append(line.strip())
    
    results['steps']['step2_sub_questions'] = sub_questions
    
    print(f"[STEP 2] Identify sub-questions or aspects:")
    print("Sub-questions:")
    for sq in sub_questions:
        print(sq)
    print("###")
    print("-" * 50)
    
    # STEP 3: Retrieve facts for each sub-question
    all_facts = {}
    
    print(f"[STEP 3] For each sub-question, retrieve relevant documents and extract useful facts.")
    
    for i, sub_question in enumerate(sub_questions, 1):
        clean_sub_q = re.sub(r'^\d+\.\s*', '', sub_question)
        
        # Use RAG system to get relevant information - FIXED: Handle response properly
        rag_prompt = f"""
        Extract relevant facts and information to answer this specific question: {clean_sub_q}
        
        Focus on factual information, specific details, numbers, dates, and key concepts.
        Present the information in a clear, organized manner.
        """
        
        try:
            rag_response = rag_system.ask(rag_prompt, clean_sub_q)
            
            # FIXED: Extract the answer from the response dictionary
            if isinstance(rag_response, dict):
                answer_text = rag_response.get('answer', '')
                if rag_response.get('error'):
                    print(f"Warning: RAG error for sub-question {i}: {rag_response['error']}")
                    answer_text = "No information available due to error."
            else:
                answer_text = str(rag_response)
            
            # Check if we have meaningful information
            if not answer_text or answer_text.strip() == "" or "No relevant documents found" in answer_text:
                print(f"Sub-question {i}: {clean_sub_q}")
                print("Relevant Facts:")
                print("  - No specific information found in the knowledge base for this query")
                all_facts[f"sub_question_{i}"] = {
                    'question': clean_sub_q,
                    'facts': ["- No specific information found in the knowledge base for this query"],
                    'raw_response': "No relevant information available"
                }
                print()
                continue
            
            # Extract facts using LLM - but handle cases where RAG returns generic "no info" responses
            if any(phrase in answer_text.lower() for phrase in [
                "cannot be found", "no information", "not available", 
                "does not contain", "cannot answer", "no relevant documents"
            ]):
                print(f"Sub-question {i}: {clean_sub_q}")
                print("Relevant Facts:")
                print("  - Information not available in current knowledge base")
                all_facts[f"sub_question_{i}"] = {
                    'question': clean_sub_q,
                    'facts': ["- Information not available in current knowledge base"],
                    'raw_response': answer_text
                }
                print()
                continue
            
            fact_extraction_prompt = f"""
            From the following information, extract 3-5 key facts that directly answer the question: "{clean_sub_q}"
            
            Information:
            {answer_text}
            
            IMPORTANT: Format your response EXACTLY as bullet points starting with a hyphen and space:
            - Fact 1
            - Fact 2
            - Fact 3
            etc.
            
            Only include facts that are directly relevant and well-supported by the information.
            Each fact should be on a separate line starting with "- ".
            
            If the information doesn't contain relevant facts, respond with:
            - No relevant facts found in the provided information
            """
            
            facts_response = clean_response(llm_instance.ask_gemini(fact_extraction_prompt))
            
            # Extract facts with better parsing
            facts = []
            for line in facts_response.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    facts.append(line)
                elif line.startswith('•'):  # Handle bullet points
                    facts.append(f"- {line[1:].strip()}")
                elif line and not line.startswith(('-', '•', '*')) and len(facts) < 5 and len(line) > 20:
                    # Only add non-bullet content if it's substantial
                    facts.append(f"- {line}")
            
            # Fallback: if no facts extracted, try to create meaningful facts from the content
            if not facts:
                # Look for sentences that contain useful information
                sentences = [s.strip() for s in answer_text.split('.') if s.strip() and len(s.strip()) > 20]
                meaningful_sentences = [s for s in sentences if not any(negative in s.lower() for negative in [
                    "no information", "cannot", "not available", "does not contain", "unable to"
                ])]
                
                if meaningful_sentences:
                    facts = [f"- {sentence}." for sentence in meaningful_sentences[:3]]
                else:
                    facts = ["- Limited information available from current knowledge base"]
            
            # Final fallback
            if not facts:
                facts = ["- No extractable facts from the retrieved information"]
            
            all_facts[f"sub_question_{i}"] = {
                'question': clean_sub_q,
                'facts': facts,
                'raw_response': answer_text  # Store the extracted answer text
            }
            
            print(f"Sub-question {i}: {clean_sub_q}")
            print("Relevant Facts:")
            for fact in facts:
                print(f"  {fact}")
            print()
            
        except Exception as e:
            print(f"Error processing sub-question {i}: {str(e)}")
            all_facts[f"sub_question_{i}"] = {
                'question': clean_sub_q,
                'facts': [f"- Error retrieving information: {str(e)}"],
                'raw_response': ""
            }
    
    results['steps']['step3_facts'] = all_facts
    print("###")
    print("-" * 50)
    
    # Main iteration loop for steps 4-6
    for iteration in range(max_iterations):
        results['iterations'] = iteration + 1
        
        # STEP 4: Reason over the information
        all_facts_text = ""
        has_meaningful_facts = False
        
        for key, value in all_facts.items():
            all_facts_text += f"Question: {value['question']}\n"
            for fact in value['facts']:
                all_facts_text += f"  {fact}\n"
                # Check if we have meaningful facts (not just "no information" messages)
                if not any(phrase in fact.lower() for phrase in [
                    "no information", "not available", "no specific information", 
                    "information not available", "no extractable facts", "limited information"
                ]):
                    has_meaningful_facts = True
            all_facts_text += "\n"
        
        # Adjust the reasoning prompt based on available information
        if has_meaningful_facts:
            step4_prompt = f"""
            [STEP 4] Reason over the retrieved information:
            
            Original Question: {user_question}
            
            Available Facts:
            {all_facts_text}
            
            Using the facts above, write a structured, reasoned answer to the full question. 
            Ensure each part of your answer is supported by the evidence provided.
            Address all aspects of the original question.
            Be comprehensive but concise.
            
            Structure your answer logically and make clear connections between the facts and your conclusions.
            """
        else:
            step4_prompt = f"""
            [STEP 4] Reason over the retrieved information:
            
            Original Question: {user_question}
            
            Available Facts:
            {all_facts_text}
            
            IMPORTANT: The knowledge base contains limited or no specific information to answer this question directly.
            
            Given the lack of specific information, craft a professional response that:
            1. Acknowledges the limitation in available information
            2. Shows understanding of what would be needed to properly evaluate the situation
            3. Demonstrates appropriate due diligence and business acumen
            4. Naturally leads to asking for the specific information needed
            
            The response should be from the perspective of a sophisticated professional who recognizes 
            when they need more information to make informed decisions.
            """
        
        draft_answer = clean_response(llm_instance.ask_gemini(step4_prompt))
        results['steps'][f'step4_draft_answer_iter_{iteration + 1}'] = draft_answer
        
        print(f"[STEP 4] Reason over the retrieved information: (Iteration {iteration + 1})")
        print("Draft Answer:")
        print(draft_answer)
        print("###")
        print("-" * 50)
        
        # STEP 5: Reflect on the answer
        step5_prompt = f"""
        [STEP 5] Reflect on the answer:
        
        Original Question: {user_question}
        Sub-questions that should be answered:
        {chr(10).join(sub_questions)}
        
        Draft Answer:
        {draft_answer}
        
        Available Facts:
        {all_facts_text}
        
        Evaluate the draft answer and check:
        1. Did I answer all sub-questions adequately?
        2. Is each claim in my answer supported by the retrieved facts?
        3. Are there contradictions or uncertainties in the information?
        4. Is there important missing information?
        
        Respond with:
        ASSESSMENT:
        - Missing info: [YES/NO] - [brief explanation if yes]
        - Contradictory info: [YES/NO] - [brief explanation if yes]  
        - Unsupported claims: [YES/NO] - [brief explanation if yes]
        - Overall quality: [GOOD/NEEDS_IMPROVEMENT]
        
        If anything needs improvement, specify what additional information should be retrieved.
        """
        
        reflection = clean_response(llm_instance.ask_gemini(step5_prompt))
        results['steps'][f'step5_reflection_iter_{iteration + 1}'] = reflection
        
        print(f"[STEP 5] Reflect on the answer: (Iteration {iteration + 1})")
        print("Reflection:")
        print(reflection)
        print("###")
        
        # Check if we need another iteration
        if "NEEDS_IMPROVEMENT" not in reflection.upper() and iteration < max_iterations - 1:
            print("Quality assessment: GOOD - Proceeding to final answer")
            break
        elif iteration < max_iterations - 1:
            print("Quality assessment: NEEDS_IMPROVEMENT - Retrieving additional information")
            # Here you could implement logic to retrieve additional information
            # For now, we'll continue with the current information
        
        print("-" * 50)
    
    # STEP 6: Final Answer
    if has_meaningful_facts:
        base_step6_prompt = f"""
        [STEP 6] Final Answer:
        
        Based on all the analysis above, provide a comprehensive, well-structured final answer to:
        "{user_question}"
        
        Your answer should:
        - Address all aspects of the original question
        - Be well-organized and easy to read
        - Include specific facts and details where relevant
        - Acknowledge any limitations or uncertainties
        - Be comprehensive yet concise
        """
    else:
        base_step6_prompt = f"""
        [STEP 6] Final Answer:
        
        Based on the analysis above, the knowledge base contains limited information to fully answer:
        "{user_question}"
        
        Provide a professional response that:
        - Acknowledges what information is available (if any)
        - Clearly states what additional information would be needed
        - Shows appropriate business judgment and due diligence
        - Demonstrates understanding of the topic area even with limited data
        - Maintains a professional, analytical tone
        """
    
    # Add custom output format if provided
    if output_format_prompt:
        step6_prompt = base_step6_prompt + f"""
        
    IMPORTANT - OUTPUT FORMAT REQUIREMENTS:
    {output_format_prompt}
    
    Make sure your final answer follows the specified format requirements above.
    """
    else:
        step6_prompt = base_step6_prompt + "\n\nThis is your final response to the user."
    
    final_answer = clean_response(llm_instance.ask_gemini(step6_prompt))
    results['steps']['step6_final_answer'] = final_answer
    results['answer'] = final_answer
    
    print(f"[STEP 6] Final Answer:")
    print(final_answer)
    print("=" * 50)
    
    return results

# Example usage function - FIXED: Proper LLM instantiation
def run_systematic_rag_example():
    """
    Example of how to use the systematic RAG function
    """
    # Initialize your systems
    rag = RAGSystem(data_folder="data", faiss_index_path="faiss_index")
    
    # Load existing system or build from scratch
    try:
        if not rag.load_existing_system():
            print("Building RAG system from scratch...")
            rag.build_from_scratch()
        else:
            print("Loaded existing RAG system")
    except Exception as e:
        print(f"Error loading system: {e}")
        print("Building RAG system from scratch...")
        rag.build_from_scratch()
    
    # FIXED: Initialize LLM properly (assuming llm is a class, not an instance)
    llm_instance = llm()
    
    # Test the RAG system with a simple query first
    print("Testing RAG system...")
    test_query = "What is cloud computing?"
    test_response = rag.query(test_query)
    print(f"Test query result: {test_response}")
    
    # Example query
    user_question = "What are the main causes of climate change and their environmental impacts?"
    
    # Example output format prompt
    output_format = """
    Format your answer as follows:
    1. Start with a brief executive summary (2-3 sentences)
    2. Use numbered sections for main points
    3. Include bullet points for sub-details
    4. End with a conclusion paragraph
    5. Use professional, academic tone
    6. Limit the total response to 300-400 words
    """
    
    # Run systematic RAG analysis with custom output format
    results = systematic_rag_query(
        user_question, 
        rag, 
        llm_instance, 
        output_format_prompt=output_format
    )
    
    return results

# Additional example function showing different output formats - FIXED
def run_systematic_rag_examples():
    """
    Multiple examples showing different output format options
    """
    rag = RAGSystem(data_folder="data", faiss_index_path="faiss_index")
    
    # FIXED: Better error handling for loading system
    if not rag.load_existing_system():
        print("Building RAG system from scratch...")
        rag.build_from_scratch()
    
    # FIXED: Proper LLM instantiation
    llm_instance = llm()
    
    # Example 1: Technical report format
    technical_format = """
    Format as a technical report:
    - Use markdown headers (##, ###)
    - Include data and statistics where available
    - Add a "Key Findings" section with bullet points
    - Include a "Limitations" section
    - Use formal, technical language
    """
    
    # Example 2: Simple FAQ format
    faq_format = """
    Format as a FAQ-style response:
    - Start with "Q: [restate the question]"
    - Follow with "A: [your answer]"
    - Use simple, conversational language
    - Break complex answers into multiple Q&A pairs if needed
    """
    
    # Example 3: Structured business brief
    business_format = """
    Format as a business brief:
    1. Executive Summary (2-3 sentences)
    2. Key Points (numbered list with brief explanations)
    3. Recommendations (if applicable)
    4. Next Steps (if applicable)
    Use clear, concise business language. Maximum 250 words.
    """
    
    question = "What are the benefits and risks of artificial intelligence in healthcare?"
    
    print("=== TECHNICAL REPORT FORMAT ===")
    result1 = systematic_rag_query(question, rag, llm_instance, technical_format)
    
    print("\n=== FAQ FORMAT ===")
    result2 = systematic_rag_query(question, rag, llm_instance, faq_format)
    
    print("\n=== BUSINESS BRIEF FORMAT ===")
    result3 = systematic_rag_query(question, rag, llm_instance, business_format)
    
    return [result1, result2, result3]

if __name__ == "__main__":
    # Run example
    results = run_systematic_rag_example()
    print("\n" + "="*50)
    print("SYSTEMATIC RAG ANALYSIS COMPLETE")
    print("="*50)