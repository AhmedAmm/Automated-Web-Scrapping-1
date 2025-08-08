import spacy
from keybert import KeyBERT
from Llm import llm  # Your RotatingGeminiClient instance
import os
from datetime import datetime
from random import randint

# Load spaCy model (download with: python -m spacy download en_core_web_sm)
nlp = spacy.load("en_core_web_sm")

# Initialize KeyBERT
kw_model = KeyBERT()

def process_with_spacy(extracted_data):
    """
    Process text content using spaCy for NLP analysis.
    
    Args:
        extracted_data (dict): Dictionary containing extracted content data
        
    Returns:
        dict: Original data enhanced with spaCy analysis
    """
    content = extracted_data.get('content', '')
    
    if not content:
        return extracted_data
    
    # Process text with spaCy
    doc = nlp(content)
    
    # Extract tokens (excluding punctuation and whitespace)
    tokens = [token.text for token in doc if not token.is_punct and not token.is_space]
    
    # Extract named entities
    entities = []
    for ent in doc.ents:
        entities.append({
            'text': ent.text,
            'label': ent.label_,
            'des²cription': spacy.explain(ent.label_)
        })
    
    # Extract POS tags
    pos_tags = []
    for token in doc:
        if not token.is_punct and not token.is_space:
            pos_tags.append({
                'text': token.text,
                'pos': token.pos_,
                'tag': token.tag_,
                'lemma': token.lemma_
            })
    
    # Extract dependency relationships
    dependencies = []
    for token in doc:
        if not token.is_punct and not token.is_space:
            dependencies.append({
                'text': token.text,
                'dep': token.dep_,
                'head': token.head.text,
                'children': [child.text for child in token.children]
            })
    
    # Add spaCy analysis to extracted_data
    extracted_data['spacy_analysis'] = {
        'tokens': tokens,
        'entities': entities,
        'pos_tags': pos_tags,
        'dependencies': dependencies,
        'sentence_count': len(list(doc.sents))
    }
    
    return extracted_data

def extract_keywords_with_keybert(extracted_data, top_k=10, keyphrase_ngram_range=(1, 3)):
    """
    Extract semantic keywords using KeyBERT.
    
    Args:
        extracted_data (dict): Dictionary containing extracted content data
        top_k (int): Number of top keywords to extract
        keyphrase_ngram_range (tuple): Range of n-grams to consider
        
    Returns:
        dict: Original data enhanced with KeyBERT keywords
    """
    content = extracted_data.get('content', '')
    
    if not content:
        return extracted_data
    
    try:
        # Extract keywords using KeyBERT
        keywords = kw_model.extract_keywords(
            content, 
            keyphrase_ngram_range=keyphrase_ngram_range, 
            stop_words='english',
            top_k=top_k,
            use_mmr=True,  # Use Maximal Marginal Relevance for diversity
            diversity=0.5
        )
        
        # Format keywords with scores
        formatted_keywords = []
        for keyword, score in keywords:
            formatted_keywords.append({
                'keyword': keyword,
                'relevance_score': round(score, 4)
            })
        
        # Add KeyBERT analysis to extracted_data
        extracted_data['keybert_analysis'] = {
            'keywords': formatted_keywords,
            'top_keyword': formatted_keywords[0]['keyword'] if formatted_keywords else None
        }
        
    except Exception as e:
        extracted_data['keybert_analysis'] = {
            'keywords': [],
            'error': str(e)
        }
    
    return extracted_data

def process_with_gemini(extracted_data):
    """
    Clean and enhance content using Gemini while preserving all original details.
    
    Args:
        extracted_data (dict): Dictionary containing extracted content data
        
    Returns:
        dict: Original data with cleaned and enhanced content
    """
    content = extracted_data.get('content', '')
    title = extracted_data.get('title', 'Unknown Title')
    
    if not content:
        return extracted_data
    
    try:
        # Clean and format the content
        cleaning_prompt = f"""
        Clean and improve the following scraped text content while preserving ALL information and details:

        Title: {title}
        Content: {content}

        Tasks:
        1. Remove any HTML artifacts, redundant whitespace, or formatting issues
        2. Fix any broken sentences or paragraph structure
        3. Correct obvious typos and grammar errors
        4. Ensure proper punctuation and capitalization
        5. Remove any navigation elements, ads, or irrelevant scraped content
        6. Keep ALL the original information and details - don't summarize or shorten
        7. Maintain the original structure and flow of the content
        8. Return only the cleaned content without any explanations

        Cleaned content:
        """
        
        cleaned_content = llm.ask_gemini(cleaning_prompt)
        
        # Enhance title if needed
        title_prompt = f"""
        Analyze this title and improve it if needed (fix capitalization, grammar, formatting):
        "{title}"
        
        If the title is already good, return it unchanged.
        If it needs improvement, return the corrected version.
        Return only the title without explanations:
        """
        
        enhanced_title = llm.ask_gemini(title_prompt)
        
        # Clean and enhance description if it exists
        enhanced_description = extracted_data.get('description')
        if enhanced_description:
            description_prompt = f"""
            Clean and improve this description while keeping all information:
            "{enhanced_description}"
            
            Fix grammar, punctuation, and formatting issues.
            Return only the cleaned description without explanations:
            """
            enhanced_description = llm.ask_gemini(description_prompt)
        
        # Update the original data with cleaned versions
        extracted_data['content'] = cleaned_content.strip()
        extracted_data['title'] = enhanced_title.strip() if enhanced_title.strip() else title
        if enhanced_description:
            extracted_data['description'] = enhanced_description.strip()
        
        # Update word and character counts with cleaned content
        cleaned_words = cleaned_content.strip().split()
        extracted_data['word_count'] = len(cleaned_words)
        extracted_data['char_count'] = len(cleaned_content.strip())
        
        # Add cleaning metadata
        extracted_data['gemini_cleaning'] = {
            'content_cleaned': True,
            'title_enhanced': enhanced_title.strip() != title if enhanced_title else False,
            'description_cleaned': bool(enhanced_description),
            'original_word_count': len(content.split()),
            'cleaned_word_count': len(cleaned_words),
            'cleaning_completed': True
        }
        
    except Exception as e:
        extracted_data['gemini_cleaning'] = {
            'content_cleaned': False,
            'cleaning_completed': False,
            'error': str(e)
        }
    
    return extracted_data

def comprehensive_nlp_processing(extracted_data):
    """
    Complete NLP pipeline combining spaCy, KeyBERT, and Gemini data cleaning.
    
    Args:
        extracted_data (dict): Dictionary containing extracted content data
        
    Returns:
        dict: Fully processed data with NLP analysis and cleaned content
    """
    # First clean the data with Gemini (this updates the content)
    processed_data = process_with_gemini(extracted_data)
    
    # Then process the cleaned content with spaCy
    processed_data = process_with_spacy(processed_data)
    
    # Extract keywords from the cleaned content with KeyBERT
    processed_data = extract_keywords_with_keybert(processed_data)
    
    # Add processing metadata
    processed_data['nlp_processing'] = {
        'gemini_cleaning_completed': 'gemini_cleaning' in processed_data,
        'spacy_completed': 'spacy_analysis' in processed_data,
        'keybert_completed': 'keybert_analysis' in processed_data,
        'processing_complete': True,
        'processing_order': ['gemini_cleaning', 'spacy_analysis', 'keybert_keywords']
    }
    
    return processed_data

# Utility function to get a clean summary of all processing results
def get_processing_summary(processed_data):
    """
    Generate a detailed RAG-ready report in markdown format with all processed data for feeding into RAG system.
    
    Args:
        processed_data (dict): Fully processed data
        
    Returns:
        str: Comprehensive markdown report for RAG ingestion
    """
    
    # Use Gemini to generate a comprehensive RAG report
    try:
        # Prepare all available data for RAG report generation
        content = processed_data.get('content', '')
        title = processed_data.get('title', '')
        url = processed_data.get('url', '')
        author = processed_data.get('author', '')
        date = processed_data.get('date', '')
        sitename = processed_data.get('sitename', '')
        description = processed_data.get('description', '')
        
        # Get keywords if available
        keywords = []
        if 'keybert_analysis' in processed_data:
            keywords = [kw['keyword'] for kw in processed_data['keybert_analysis'].get('keywords', [])]
        
        # Get entities if available
        entities = []
        if 'spacy_analysis' in processed_data:
            entities = [ent['text'] for ent in processed_data['spacy_analysis'].get('entities', [])]
        
        # Create comprehensive RAG report using Gemini
        rag_report_prompt = f"""
        Create a comprehensive, detailed markdown report for RAG (Retrieval Augmented Generation) system ingestion. This report should be as detailed and informative as possible to provide maximum context for future queries.

        Source Information:
        - Title: {title}
        - URL: {url}
        - Author: {author}
        - Date: {date}
        - Site: {sitename}
        - Description: {description}
        - Keywords: {', '.join(keywords)}
        - Named Entities: {', '.join(entities)}

        Main Content:
        {content}

        INSTRUCTIONS: Analyze the provided document and create a detailed markdown report. Only include sections that contain relevant information found in the document. If a section has no relevant content, skip it entirely - do not create empty sections or mention that information is unavailable.

        Generate a detailed markdown RAG report with the following structure (include only applicable sections):

        ## Document Overview
        Comprehensive summary of what this document contains, its purpose, and main themes
        
        ## Key Topics and Concepts
        Detailed breakdown of all major topics, concepts, theories, methodologies, or subjects covered
        
        ## Important Facts and Data
        All specific facts, statistics, dates, numbers, research findings, or data points mentioned
        
        ## People and Organizations
        All individuals, companies, organizations, institutions mentioned with their roles and context
        
        ## Technical Information
        Any technical details, processes, procedures, specifications, or methodologies
        
        ## Context and Background
        Historical context, background information, related events or developments
        
        ## Conclusions and Insights
        Key conclusions, insights, recommendations, or implications presented
        
        ## Relationships and Connections
        How this content relates to broader topics, trends, or other concepts
        
        ## Actionable Information
        Any actionable advice, steps, guidelines, or instructions provided
        
        ## Future Implications
        Any predictions, future trends, or forward-looking statements

        ## Company Values and Business Philosophy
        Core values, principles, philosophical approaches to business, preferred methodologies, cultural preferences, decision-making criteria, risk tolerance, innovation approaches, market positioning beliefs, customer service philosophy, and leadership principles

        ## Professional Profiles and Career Information
        Job titles, roles, responsibilities, professional backgrounds, experience levels, educational qualifications, certifications, career progression, industry expertise, skills, competencies, achievements, team structures, organizational hierarchy, and professional networks

        ## Work Processes and Methodologies
        Specific work processes, project management approaches, quality control procedures, collaboration methods, team workflows, tools and technologies, deliverable formats, timeline management, communication protocols, performance measurement, client interaction processes, documentation standards, and service delivery models

        ## Product Analysis and Market Information
        Product specifications, features, pricing details, market positioning, target audience, product reviews, customer feedback, market performance, sales data, distribution channels, product lifecycle information, competitive pricing analysis, and market reception

        ## Competitive Landscape
        Direct competitors, competing products and services, alternative solutions, market players, competitive positioning, feature comparisons, market share data, competitor strengths and weaknesses, competitive threats, pricing comparisons, and competitive advantages

        ## Client Relationships and Partnerships
        Client profiles, partnership agreements, collaboration details, business relationships, customer segments, client success stories, partnership outcomes, joint ventures, strategic alliances, supplier relationships, vendor partnerships, and stakeholder engagement

        ## Business Intelligence and Market Analysis
        Market trends, industry analysis, customer preferences, market research findings, business performance metrics, growth opportunities, market challenges, industry forecasts, competitive intelligence, and strategic market insights

        ## Challenges and Risk Factors
        Business challenges, market risks, operational difficulties, competitive threats, regulatory challenges, financial risks, technical limitations, market barriers, organizational challenges, and strategic risks

        FORMATTING REQUIREMENTS:
        1. Use proper markdown formatting with headers, bullet points, and tables where appropriate
        2. Include specific details, exact quotes, and concrete examples when valuable
        3. Maintain factual accuracy and base all content on information explicitly stated in the source document
        4. Be comprehensive and detailed - include every important detail that could be relevant for future queries
        5. Only create sections that have relevant content from the document
        6. Do not create placeholder text or mention missing information
        7. do not write mention in the document write instead the details of the document that is relevent to the part you are talking about


        Generate only the markdown content without any explanation or meta-commentary:
        """
        
        gemini_report = llm.ask_gemini(rag_report_prompt)
        
        # Build comprehensive markdown document
        markdown_report = f"""# RAG Document Report

## Source Metadata

| Field | Value |
|-------|-------|
| **Title** | {title} |
| **URL** | {url} |
| **Author** | {author or 'Not specified'} |
| **Publication Date** | {date or 'Not specified'} |
| **Site Name** | {sitename or 'Not specified'} |
| **Description** | {description or 'Not specified'} |
| **Word Count** | {processed_data.get('word_count', 0)} |
| **Character Count** | {processed_data.get('char_count', 0)} |

## Semantic Keywords

"""
        
        # Add keywords section
        if keywords:
            keyword_list = []
            if 'keybert_analysis' in processed_data:
                for kw_data in processed_data['keybert_analysis'].get('keywords', []):
                    keyword_list.append(f"- **{kw_data['keyword']}** (relevance: {kw_data['relevance_score']})")
            markdown_report += '\n'.join(keyword_list)
        else:
            markdown_report += "No keywords extracted."
        
        # Add named entities section
        markdown_report += "\n\n## Named Entities\n\n"
        if 'spacy_analysis' in processed_data:
            entities_data = processed_data['spacy_analysis'].get('entities', [])
            if entities_data:
                entity_table = "| Entity | Type | Description |\n|--------|------|-------------|\n"
                for ent in entities_data:
                    entity_table += f"| {ent['text']} | {ent['label']} | {ent['description']} |\n"
                markdown_report += entity_table
            else:
                markdown_report += "No named entities detected."
        else:
            markdown_report += "Named entity analysis not performed."
        
        # Add linguistic analysis
        markdown_report += "\n\n## Linguistic Analysis\n\n"
        if 'spacy_analysis' in processed_data:
            spacy_data = processed_data['spacy_analysis']
            markdown_report += f"- **Sentences**: {spacy_data.get('sentence_count', 0)}\n"
            markdown_report += f"- **Tokens**: {len(spacy_data.get('tokens', []))}\n"
            markdown_report += f"- **Named Entities**: {len(spacy_data.get('entities', []))}\n"
            
            # Add POS distribution if available
            pos_tags = spacy_data.get('pos_tags', [])
            if pos_tags:
                pos_counts = {}
                for pos_info in pos_tags:
                    pos = pos_info.get('pos', 'UNKNOWN')
                    pos_counts[pos] = pos_counts.get(pos, 0) + 1
                
                markdown_report += "\n### Part-of-Speech Distribution\n\n"
                for pos, count in sorted(pos_counts.items(), key=lambda x: x[1], reverse=True):
                    markdown_report += f"- **{pos}**: {count}\n"
        else:
            markdown_report += "Linguistic analysis not performed."
        
        # Add processing metadata
        markdown_report += "\n\n## Processing Metadata\n\n"
        if 'gemini_cleaning' in processed_data:
            cleaning_data = processed_data['gemini_cleaning']
            markdown_report += "### Data Quality Indicators\n\n"
            markdown_report += f"- **Content Cleaned**: {cleaning_data.get('content_cleaned', False)}\n"
            markdown_report += f"- **Title Enhanced**: {cleaning_data.get('title_enhanced', False)}\n"
            markdown_report += f"- **Description Cleaned**: {cleaning_data.get('description_cleaned', False)}\n"
            markdown_report += f"- **Original Word Count**: {cleaning_data.get('original_word_count', 0)}\n"
            markdown_report += f"- **Final Word Count**: {cleaning_data.get('cleaned_word_count', 0)}\n"
            
            if cleaning_data.get('original_word_count', 0) > 0:
                improvement_ratio = cleaning_data.get('cleaned_word_count', 0) / cleaning_data.get('original_word_count', 1)
                markdown_report += f"- **Content Improvement Ratio**: {improvement_ratio:.3f}\n"
        
        # Add tools used
        tools_used = []
        if 'spacy_analysis' in processed_data:
            tools_used.append("spaCy (NLP Analysis)")
        if 'keybert_analysis' in processed_data:
            tools_used.append("KeyBERT (Semantic Keywords)")
        if 'gemini_cleaning' in processed_data:
            tools_used.append("Gemini (Content Cleaning)")
        
        markdown_report += f"\n### NLP Tools Used\n\n"
        for tool in tools_used:
            markdown_report += f"- {tool}\n"
        
        # Add the main Gemini-generated content analysis
        markdown_report += f"\n\n---\n\n{gemini_report.strip()}\n\n---\n\n"
        
        # Add full content section
        markdown_report += f"""## Full Content

{content}

---

## Search Terms for RAG Retrieval

"""
        
        # Generate comprehensive search terms
        all_terms = set()
        all_terms.update(keywords)
        if 'spacy_analysis' in processed_data:
            all_terms.update([ent['text'].lower() for ent in processed_data['spacy_analysis'].get('entities', [])])
        if title:
            all_terms.update(title.lower().split())
        if description:
            all_terms.update(description.lower().split())
        
        # Remove short terms and clean up
        clean_terms = [term for term in all_terms if len(term) > 2 and term.isalpha()]
        clean_terms.sort()
        
        for term in clean_terms:  # Limit to top 50 terms
            markdown_report += f"- {term}\n"
        
        markdown_report += f"\n**Generated on**: {processed_data.get('processing_date', 'Unknown date')}"
        
        return markdown_report.strip()
        
    except Exception as e:
        # Fallback: return basic markdown if Gemini fails
        return f"""# RAG Document Report - Error

## Source Information
- **Title**: {processed_data.get('title', 'Unknown')}
- **URL**: {processed_data.get('url', 'Unknown')}
- **Word Count**: {processed_data.get('word_count', 0)}

## Error
Report generation failed: {str(e)}

## Content
{processed_data.get('content', 'No content available')}
"""     



def generate_market_intelligence_summary(processed_nlp_data):
    """
    Generate a comprehensive markdown summary using Gemini for market intelligence and RAG feeding.
    
    Args:
        processed_nlp_data (dict): Output from comprehensive_nlp_processing function
        
    Returns:
        str: Markdown formatted summary containing market intelligence data
    """
    
    # Extract relevant data from processed NLP results
    content = processed_nlp_data.get('content', '')
    spacy_analysis = processed_nlp_data.get('spacy_analysis', {})
    keybert_keywords = processed_nlp_data.get('keybert_analysis', {}).get('keywords', [])
    gemini_cleaning = processed_nlp_data.get('gemini_cleaning', {})
    
    # Prepare entities and keywords for context
    entities = spacy_analysis.get('entities', [])
    entity_text = ", ".join([f"{ent['text']} ({ent['label']})" for ent in entities])
    keyword_text = ", ".join([f"{kw[0]} (score: {kw[1]:.2f})" for kw in keybert_keywords])
    
    # Create comprehensive prompt for Gemini
    prompt = f"""
You are a market intelligence analyst. Analyze the following scraped content and generate a comprehensive markdown summary for RAG (Retrieval-Augmented Generation) system feeding. Focus on extracting actionable business intelligence.

SCRAPED CONTENT:
{content}

EXTRACTED ENTITIES: {entity_text}
KEY KEYWORDS: {keyword_text}

Please create a detailed markdown summary organized into the following sections. Extract and structure ALL relevant information found in the content:

## Company Overview
- Company name(s) and basic information
- Business model and core activities
- Market position and reputation
- Company size, employees, and organizational structure (if mentioned in document)

## Products & Services
- Product names and descriptions
- Service offerings and characteristics  
- Product features and specifications
- Pricing information (if available in document)
- Product categories and variants
- Launch dates and product roadmap (if mentioned in document)

## Competitive Landscape
- Direct competitors mentioned (if present in document)
- Indirect competitors and alternative solutions (if mentioned in document)
- Competitive advantages/disadvantages
- Market positioning vs competitors
- Competitive threats and opportunities
- Competitor pricing and strategies (if discussed in document)
- Market share information (if available in document)

## Competitor Analysis
- Specific competitor names and profiles (if mentioned in document)
- Competitor strengths and weaknesses
- Competitor product offerings and features
- Competitor customer base and market approach
- Competitive differentiators and unique selling propositions
- Competitor financial performance or market metrics (if available)

## Target Market & Clients
- Target customer segments
- Client demographics and profiles
- Customer job roles and industries
- Market size and segments (if specified in document)
- Geographic markets served
- Customer acquisition strategies (if mentioned in document)

## Customer Experience & Feedback
- Client testimonials and reviews
- Customer satisfaction levels
- Pain points and complaints
- Service experience quality
- Support and customer service feedback
- Customer retention rates (if mentioned in document)

## Work Methods and Deliverables
- Service delivery process
- Operational workflows and methodologies
- Specific deliverables provided to clients
- Quality control measures
- Technology stack and tools used (if mentioned in document)
- Project management or execution approaches (if mentioned in document)

## Market Analysis
- Market trends mentioned (if present in document)
- Industry insights
- Growth opportunities
- Market challenges
- Regulatory environment
- Market size and growth projections (if available in document)

## Financial Information
- Revenue figures and financial performance (if mentioned in document)
- Funding information and investors
- Pricing models and cost structures
- Financial growth metrics
- Investment and expansion plans

## Issues & Controversies
- Scandals or negative incidents
- Regulatory issues
- Public relations problems
- Legal challenges
- Reputation risks
- Crisis management responses (if mentioned in document)

## Client Company Preferences and Beliefs
- Strategic or cultural preferences (e.g., innovation focus, risk tolerance)
- Core beliefs or values influencing decision-making
- Preferred vendor or partner characteristics
- Philosophical or operational principles (if mentioned in document)
- Alignment with industry trends or standards
- Specific priorities or biases (if discussed in document)

## Client Requirements
- Practical client needs and expectations
- Preferred service characteristics
- Decision-making criteria
- Budget considerations
- Service delivery expectations
- Buying process and decision timelines (if mentioned in document)

## Partnership & Ecosystem
- Strategic partnerships and alliances (if mentioned in document)
- Technology integrations
- Channel partners and distribution networks
- Vendor relationships
- Ecosystem positioning

## Key Insights for RAG System
- Most important takeaways
- Critical data points for competitive analysis
- Essential information for customer targeting
- Key metrics and performance indicators
- Strategic recommendations based on content analysis

IMPORTANT INSTRUCTIONS:
1. Use proper markdown formatting with headers, bullet points, and emphasis
2. Extract specific names, numbers, and concrete details
3. For each section, ONLY include information that is explicitly mentioned or discussed in the source document
4. If information is not available in a section, write "No specific information available in source document"
5. When presenting information, indicate its source within the document by adding "(mentioned in document)" after key facts
6. Focus on actionable intelligence that can be used for business decisions
7. Maintain factual accuracy - only include information actually present in the content
8. Structure data for easy retrieval by RAG systems
9. Include relevant quotes or specific statements when valuable, using quotation marks
10. Clearly distinguish between direct facts and inferred insights
11. If competitor information is mentioned, dedicate special attention to extracting all competitive intelligence
12. Cross-reference entities and keywords with the content to ensure comprehensive coverage
"""

    try:
        # First, generate document summary for header
        summary_prompt = f"""
Analyze the following content and create a concise executive summary (2-3 paragraphs) that captures the essence of this document. Focus on:
- What type of document/content this is
- Key companies, products, or services mentioned
- Main business insights or themes
- Overall purpose and value of the information

CONTENT TO SUMMARIZE:
{content}...

KEYWORDS: {keyword_text}
ENTITIES: {entity_text}

Provide a clear, professional summary that would help someone quickly understand what this document contains and its business relevance.
"""
        
        document_summary = llm.ask_gemini(summary_prompt)
        
        # Get main Gemini response
        gemini_response = llm.ask_gemini(prompt)
        
        # Add metadata header with document summary
        metadata_header = f"""# Market Intelligence Summary

## Document Overview
{document_summary}

---

"""
        
        # Combine metadata with Gemini summary
        final_summary = metadata_header + gemini_response
        
        return final_summary
        
    except Exception as e:
        # Fallback summary if Gemini fails
        fallback_summary = f"""# Market Intelligence Summary - Processing Error

**Error:** Could not generate summary using Gemini: {str(e)}

## Available Data
- Content Length: {len(content)} characters
- Keywords: {keyword_text}
- Entities: {entity_text}

## Raw Content Preview
{content}...

*Note: Full analysis could not be completed due to processing error.*
"""
        return fallback_summary




def data_cleaning(dirty_data ,output_filename=None):
    """
    Process dirty data and save the processing report as a markdown file.
    
    Args:
        dirty_data: Input data to be processed
        output_filename (str, optional): Custom filename for the output file.
                                       If None, uses timestamp-based naming.
    
    Returns:
        str: Path to the saved markdown file
    """
    # Process the data
    processed = comprehensive_nlp_processing(dirty_data)
    report = generate_market_intelligence_summary(processed)
    
    # Create data folder if it doesn't exist
    data_folder = "data"
    os.makedirs(data_folder, exist_ok=True)
    
    # Generate filename if not provided
    if output_filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S"+str(randint(1, 9999)))
        output_filename = f"processing_report_{timestamp}.md"
    
    # Ensure the filename has .md extension
    if not output_filename.endswith('.md'):
        output_filename += '.md'
    
    # Full path for the output file
    output_path = os.path.join(data_folder, output_filename)
    
    # Write the markdown file (report is already in markdown format)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"Processing report saved to: {output_path}")
    return output_path