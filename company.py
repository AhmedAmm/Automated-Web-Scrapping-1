from Queries import generate_competitor_queries,generate_client_research_queries,_parse_queries
from Search import get_urls
from scrap1 import scrape_urls,cleanup_all
from rag1 import RAGSystem
from iterative_rag import systematic_rag_query
from Llm import llm
import asyncio


async def company_search(company):
    try:
        # First phase: Competitor research
        # print(f"Starting competitor research for {company}...")
        # queries = generate_competitor_queries(company)
        # urls = get_urls(queries)
        
        # # Use optimized scraper with concurrent processing
        # await scrape_urls(urls, max_concurrent=20)  # Added max_concurrent parameter
        
        # # Build RAG system for competitor analysis
        rag= RAGSystem("data", "faiss_index")
        rag.build_from_scratch()
        rag.load_existing_system()
        
        COMPETITOR_FINDER_PROMPT = """
        You are a business intelligence analyst specializing in competitive analysis. Your task is to identify and list all competitors of the given company based on the retrieved documents and market intelligence data.

        COMPANY TO ANALYZE: {company}

        INSTRUCTIONS:
        1. Search through all retrieved documents for any mentions of competitors, competitive landscape, market players, or alternative solutions
        2. Identify both DIRECT competitors (same products/services, same target market) and INDIRECT competitors (alternative solutions, adjacent markets)
        3. Look for competitor mentions in sections like:
        - Competitive landscape
        - Market analysis
        - Company comparisons
        - Customer alternatives
        - Industry players
        - Partnership mentions
        - Acquisition targets

        OUTPUT FORMAT:
        Provide ONLY a bullet-point list of competitor names. Use this exact format:

        • [Competitor Name 1]
        • [Competitor Name 2]  
        • [Competitor Name 3]
        • [Competitor Name 4]
        ...and so on

        IMPORTANT RULES:
        - List ONLY actual company names that are explicitly mentioned in the documents as competitors or market players
        - Do NOT include the target company itself in the list
        - Do NOT include customers, partners, or suppliers unless they are also competitors
        - Do NOT add explanations, categories, or additional text
        - Do NOT include companies that are only mentioned in passing without competitive context
        - If no competitors are found in the documents, respond with: "No competitors identified in available documents"
        - Include both public companies and startups if mentioned
        - Remove any duplicates from your list
        - Maintain consistent formatting with bullet points (•)
        - return the top 10 competitors by the criteria of how big the company is 

        FOCUS ON ACCURACY:
        Only include companies that are clearly identified in the retrieved documents as competing in the same or adjacent market space. Do not make assumptions or add companies not explicitly mentioned in the source material.
        """
        
        print("Analyzing competitors...")
        respond = rag.ask(COMPETITOR_FINDER_PROMPT, "query: what are the competitors of " + company + "? ")
        company_list = _parse_queries(respond["answer"])
        print(f"Found competitors: {company_list}")
        
        # # Second phase: Client research
        # print("Starting client research...")
        # queries = generate_client_research_queries(company_list)
        # urls = get_urls(queries)
        
        # # Use optimized scraper again with concurrent processing
        # await scrape_urls(urls, max_concurrent=10)  # Added max_concurrent parameter
        

        # rag.cleanup()
        # # Create separate RAG system for client analysis
        # rag = RAGSystem("data", "faiss_index1")
        # rag.build_from_scratch()
        # rag.load_existing_system()

        
        # CLIENT_FINDER_PROMPT = """
        #  You are a business intelligence analyst specializing in client identification and market analysis. Your task is to identify and list all current clients, past clients, and potential clients of the given company based on the retrieved documents and market intelligence data.

        #  COMPANY TO ANALYZE: {company}

        # INSTRUCTIONS:
        # 1. Search through all retrieved documents for any mentions of clients, customers, partnerships, case studies, or business relationships
        # 2. Identify three categories:
        # - CURRENT CLIENTS (active customers, ongoing partnerships)
        # - PAST CLIENTS (former customers, completed projects, historical relationships)
        # - POTENTIAL CLIENTS (prospects, competitor clients, target market companies)
        # 3. Look for client mentions in sections like:
        # - Case studies and success stories
        # - Client testimonials and reviews
        # - Partnership announcements
        # - Project references
        # - Contract wins and deals
        # - Industry client lists
        # - Competitor client bases (as potential targets)
        # - Market analysis and target segments

        # OUTPUT FORMAT:
        # Provide ONLY a bullet-point list of client names organized by category. Use this exact format:

        # CURRENT CLIENTS:
        # - [Client Name 1]
        # - [Client Name 2]
        # - [Client Name 3]
        # ...

        # PAST CLIENTS:
        # - [Former Client Name 1]
        # - [Former Client Name 2]
        # - [Former Client Name 3]
        # ...

        # POTENTIAL CLIENTS:
        # - [Prospect/Competitor Client Name 1]
        # - [Prospect/Competitor Client Name 2]
        # - [Prospect/Competitor Client Name 3]
        # ...

        # IMPORTANT RULES:
        # - If no clients are found in any category, respond with: "No clients identified in available documents" for that category
        # - Include both enterprise clients and smaller businesses if mentioned
        # - Remove any duplicates within each category
        # - Maintain consistent formatting with bullet points (•)
        # - For potential clients, include competitor clients that could be prospects for the target company

        # FOCUS ON ACCURACY:
        # Only include companies that are clearly identified in the retrieved documents. Do not make assumptions or add companies not explicitly mentioned in the source material.
        # """
        
        # # print("Analyzing clients...")
        # # ch=company
        # # for tot in company_list:
        # #     ch+=tot+", "
        # # client_analysis = rag1.ask(CLIENT_FINDER_PROMPT, f"query: what are the clients of {ch}?")
        # # print(client_analysis["answer"])

        # result=systematic_rag_query("what are the target client ,potential client and the client of {company}?",rag,llm,CLIENT_FINDER_PROMPT)
        # print(result["answer"])
        # rag.cleanup()
        
    except Exception as e:
        print(f"Error in company_search: {str(e)}")
        raise
    
    finally:
        # Always cleanup resources
        print("Cleaning up resources...")
        await cleanup_all()
        print("Company search completed.")


async def main():
    # Replace "talan" with whatever company you want to search
    await company_search("talan")

if __name__ == "__main__":
    asyncio.run(main())
