from Llm import llm

def generate_competitor_queries(company_name):    
    prompt = f"""
    Generate a list of 5 high-quality, detailed search queries designed to discover **competitors of {company_name}** using search engines and business intelligence tools (Google Search, Google Alerts, Talkwalker, etc.).

    Focus of Queries:
    - Identify **direct and indirect competitors** of {company_name}
    - Discover **similar companies**, **alternative providers**, and **market challengers**
    - Surface **lists**, **rankings**, **industry comparisons**, and **competitive maps**
    - Target both **global** and **regional** competitors
    - Include **emerging players**, **startups**, and **niche alternatives**

    Requirements:
    - Use comparative and discovery-based phrasing (e.g., “top competitors of {company_name}”, “alternatives to {company_name}”, “{company_name} similar companies”)
    - Ensure all queries are **long and specific** (no short or generic phrases)
    - Focus only on finding competitors — do not include pricing, SWOT, or reviews unless it helps **reveal competitor names**
    - Output a **numbered list** with **only the queries**

    Example output format:
    . Query 1  
    . Query 2  
    . Query 3  
    ...

    Only return the list of queries — no explanations, descriptions, or comments.
    """


    
    try:
        response = llm.ask_gemini(prompt)
        queries = _parse_queries(response)
        
        print(f"Generated {len(queries)} strategic monitoring queries for {company_name}")
        return queries
        
    except Exception as e:
        print(f"Error generating queries for {company_name}: {e}")
        return []
    


def generate_client_research_queries(company_list):
    all_queries = []
    
    for company_name in company_list:
        prompt = f"""
        Generate a list of 4 high-quality, detailed search queries designed to discover comprehensive information about **{company_name}** clients, customer experiences, and reputation issues.

        Focus Areas:

        **CLIENT IDENTIFICATION & RELATIONSHIPS (1 queries):**
        - Identify **current and past clients** of {company_name}
        - Discover **major enterprise customers** and **key client accounts**
        - Find **client partnership announcements** and **contract wins**
        - Uncover **strategic alliances** and **joint ventures**
        - Surface **"who uses {company_name}"** and **client case studies**

        **TARGET CLIENT RESEARCH (1 query):**
        - Identify **{company_name}'s target market** and **ideal client profile**
        - Discover **industry focus areas** and **client acquisition strategies**
        - Find **marketing materials** targeting specific client segments
        - Uncover **sales presentations** and **client onboarding processes**
        - Surface **competitive positioning** against client alternatives

        **Product services {company_name} they provide(2 queries)
        - identify the services and the product that the {company_name} provides with description
        - feed back about their Product or services

        Requirements:
        - Use specific, targeted phrasing (e.g., "{company_name} client list")
        - Ensure all queries are **long and specific** with relevant keywords
        - Target both **recent** and **historical** information
        - Output a **numbered list** with **only the queries**

        Example output format:
        1. Query 1
        2. Query 2
        3. Query 3
        ...

        Only return the list of queries — no explanations, descriptions, or comments.
        """
        
        try:
            response = llm.ask_gemini(prompt)
            queries = _parse_queries(response)
            all_queries.extend(queries)
            
            print(f"Generated {len(queries)} client research queries for {company_name}")
            
        except Exception as e:
            print(f"Error generating queries for {company_name}: {e}")
    
    print(f"Completed query generation for {len(company_list)} companies - Total queries: {len(all_queries)}")
    return all_queries



def generate_product_competitor_queries(product_name, product_description):
    all_queries = []
    
            
    prompt = f"""
        Generate a list of 10 high-quality, detailed search queries designed to discover comprehensive competitive intelligence about **{product_name}** (Description: {product_description}) using search engines and business intelligence tools.

        Focus Areas:
        
        **DIRECT COMPETITORS & ALTERNATIVES (4 queries):**
        - Identify **direct competitors** and **alternative products** to {product_name}
        - Discover **similar products**, **substitute solutions**, and **competing offerings**
        - Find **market comparisons**, **feature comparisons**, and **head-to-head analyses**
        - Surface **"vs" comparisons** and **alternative recommendation lists**
        - Target both **established players** and **emerging alternatives**
        - Include **budget alternatives** and **premium alternatives**

        **COMPETITIVE ANALYSIS & MARKET INTELLIGENCE (4 queries):**
        - **Market share analysis** and **competitive positioning** of {product_name}
        - **SWOT analysis**, **competitive advantages**, and **weakness assessments**
        - **Industry reports**, **market research**, and **analyst opinions**
        - **Competitive landscape maps** and **market leader rankings**
        - **Feature gap analysis** and **competitive differentiation studies**
        - **Pricing comparisons** and **value proposition analysis**

        **FAILURES, SCANDALS & NEGATIVE INTELLIGENCE (2 queries):**
        - **Product failures**, **recalls**, and **quality issues** with {product_name}
        - **Scandals**, **controversies**, and **negative press** involving {product_name}
        - **Failed versions**, **discontinued models**, and **product flops**
        - **Security vulnerabilities**, **privacy concerns**, and **data breaches**
        - **Legal issues**, **lawsuits**, and **regulatory problems**
        - **Customer complaints**, **negative reviews**, and **criticism**

        Requirements:
        - Use specific, targeted phrasing (e.g., " alternatives", " vs competitors", " failed versions")
        - Ensure all queries are **long and specific** with relevant keywords from the product description
        - Focus on discovering **actionable competitive intelligence**
        - Target both **recent** and **historical** information
        - Include **technical specifications** and **performance comparisons** when relevant
        - Output a **numbered list** with **only the queries**

        Example output format:
        . Query 1
        . Query 2
        . Query 3
        ...

        Only return the list of queries — no explanations, descriptions, or comments.
        """
        
    try:
        response = llm.ask_gemini(prompt)
        queries = _parse_queries(response)
        all_queries.extend(queries)
            
        print(f"Generated {len(queries)} competitive intelligence queries for {product_name}")
            
    except Exception as e:
        print(f"Error generating queries for {product_name}: {e}")
    
    return all_queries



def generate_client_profile_queries(client_name):
    
    all_queries = []
    
            
    prompt = f"""
        Generate a list of 9 high-quality, detailed search queries designed to discover comprehensive profile information about **{client_name}** using search engines, social media platforms, and professional networks.

        Focus Areas:
        
        **PREFERENCES & BELIEFS (3 queries):**
        - Discover **personal preferences**, **likes**, and **interests** of {client_name}
        - Find **beliefs**, **values**, and **ideological positions** expressed by {client_name}
        - Identify **brand preferences**, **technology choices**, and **vendor preferences**
        - Surface **lifestyle preferences**, **hobbies**, and **personal interests**
        - Uncover **political views**, **social causes**, and **advocacy positions**
        - Find **communication preferences** and **decision-making style**

        **PROFESSIONAL PROFILE & JOB DETAILS (3 queries):**
        - Detailed information about **current job title**, **role**, and **responsibilities** of {client_name}
        - **Career history**, **previous positions**, and **professional background**
        - **Company information**, **industry sector**, and **organizational structure**
        - **Professional achievements**, **awards**, and **recognition**
        - **Skills**, **expertise areas**, and **specializations**
        - **Professional network**, **connections**, and **industry associations**

        **WORK METHODS & DELIVERABLES (3 queries):**
        - **Work methodologies**, **processes**, and **approaches** used by {client_name}
        - **Project deliverables**, **outputs**, and **work products** created by {client_name}
        - **Management style**, **leadership approach**, and **team collaboration methods**
        - **Tools**, **software**, and **technologies** used in their work
        - **Work philosophy**, **best practices**, and **professional standards**
        - **Client testimonials** about {client_name}'s **work quality** and **delivery methods**

        Requirements:
        - Use specific, targeted phrasing (e.g., "{client_name} preferences", "{client_name} work methodology", "{client_name} professional background")
        - Ensure all queries are **long and specific** with relevant professional and personal keywords
        - Include platform-specific searches (LinkedIn, Twitter, company websites, industry publications)
        - Focus on discovering **actionable insights** about the client's profile
        - Target both **recent** and **historical** information
        - Include **social media mentions**, **interviews**, and **public statements**
        - Output a **numbered list** with **only the queries**

        Example output format:
        . Query 1
        . Query 2
        . Query 3
        ...

        Only return the list of queries — no explanations, descriptions, or comments.
        """
        
    try:
        response = llm.ask_gemini(prompt)
        queries = _parse_queries(response)
        all_queries.extend(queries)
            
        print(f"Generated {len(queries)} client profile queries for {client_name}")
            
    except Exception as e:
        print(f"Error generating queries for {client_name}: {e}")
    
    return all_queries

def _parse_queries(response):
    """Parse queries from Gemini response"""
    queries = []
    lines = response.split('\n')
    
    for line in lines:
        line = line.strip()
        if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
            # Clean the query
            query = line
            # Remove numbering and bullet points
            prefixes = ['.','-', '•', '*']
            
            for prefix in prefixes:
                if query.startswith(prefix):
                    query = query[len(prefix):].strip()
                    break
            
            queries.append(query)
    
    return queries


def generate_all_queries(user_company,user_product_name,user_product_description,client_company,client_industry,company_size):    
    prompt = f"""
    You are a knowledgeable and detail-oriented research assistant.

    Your task is to generate exactly 26 **realistic and high-quality web search queries** for collecting context-rich information used in a retrieval-augmented generation (RAG) system. These queries will be used to gather comprehensive intelligence for an upcoming client engagement.

    ### Inputs:
    - user_company: {user_company}
    - user_product_name: {user_product_name}
    - user_product_description: {user_product_description}
    - client_company: {client_company}
    - client_industry: {client_industry}
    - company_size: {company_size}

    ### Output Requirements:
    1. Generate **exactly 2 realistic search queries for each of the 13 categories** below (total = 26 queries).
    2. Each query **must be phrased naturally as if typed into a search engine** (e.g., “{user_product_name} case studies in manufacturing sector”).
    3. Use at least one placeholder in every query (e.g., {user_company}, {user_product_name}, {client_company}, etc.).
    4. Ensure the queries align with the intelligence needs outlined below.

    ---

    ### 13 Categories of Intelligence (2 queries each):

    **A. Vendor Analysis (→ `vendor_analysis`)**  
    Focus: {user_company}'s background, reputation, market position, customer base, financial health.

    **B. Product Deep Dive (→ `product_deep_dive`)**  
    Focus: {user_product_name}'s features, pricing, updates, technical specs, customer support, use cases.

    **C. Competitive Landscape (→ `competitive_landscape`)**  
    Focus: Competitor comparison for {user_product_name}, market positioning, differentiators.

    **D. Industry Context (→ `industry_context`)**  
    Focus: Trends, regulations, pain points, and procurement practices in the {client_industry} sector.

    **E. Client Segment Analysis (→ `client_segment_analysis`)**  
    Focus: Needs, challenges, and buying behavior of companies of size {company_size} in {client_industry}.

    **F. Implementation Realities (→ `implementation_realities`)**  
    Focus: Real-world adoption of {user_product_name}, common blockers, timeline, success factors.

    **G. ROI & Value Justification (→ `roi_and_value`)**  
    Focus: Measurable outcomes, ROI benchmarks, case studies, value frameworks for {user_product_name}.

    **H. Sales & Procurement (→ `sales_process`)**  
    Focus: Enterprise buying journeys, typical procurement cycles, RFP processes in {client_industry}.

    **I. Tech & Integration Ecosystem (→ `integration_ecosystem`)**  
    Focus: {user_product_name}'s integration capabilities, ecosystem compatibility, API strengths.

    **J. Market Research & Analyst Views**  
    Focus: Analyst reports, market sizing, forecast trends, Gartner/Forrester insights for {user_product_name} or {client_industry}.

    **K. {client_company} Culture & Beliefs**  
    Focus: Public statements, leadership interviews, hiring patterns, core values of {client_company}.

    **L. Negative Intel on {user_product_name}**  
    Focus: Known issues, failed implementations, customer complaints, lawsuits, or scandals.

    **M. {client_company} Work Style & Deliverables**  
    Focus: Project execution style, deliverable formats, vendor expectations, recent partnerships.

    ---

    ### Output Format:
    Return only a numbered list from 1 to 26 — one line per search query.

    **Example format:**
    1. {user_company} financial stability and investor confidence  
    2. common customer complaints about {user_product_name} in tech forums  
    ...  
    26. how {client_company} defines success in technology partnerships

    """


    try:
        response = llm.ask_gemini(prompt)
        queries = _parse_queries(response)
        
        print(f"Generated {len(queries)}")
        return queries
        
    except Exception as e:
        print(f"Error generating queries: {e}")
        return []
    
