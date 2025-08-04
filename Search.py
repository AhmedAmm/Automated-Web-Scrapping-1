import os
from exa_py import Exa
import requests
import time
from typing import List

def get_urls(queries : list, num_results=5, type="auto", include_domains=None, exclude_domains=None):
    # Get EXA API key from environment
    api_key = os.getenv('exa_key')
    if not api_key:
        raise ValueError("EXA_API_KEY environment variable not set")
    
    # Initialize EXA client
    exa = Exa(api_key=api_key)
    
    all_urls = []
    
    # Search each query
    for query in queries:
        try:
            result = exa.search(
                query=query,
                num_results=num_results,
                type=type,
                include_domains=include_domains,
                exclude_domains=exclude_domains
            )
            urls = [r.url for r in result.results]
            all_urls.extend(urls)
        except Exception as e:
            return search_and_add_urls(queries,all_urls)
    
    # Remove duplicates
    unique_urls = list(set(all_urls))
    
    return unique_urls





def search_and_add_urls(queries: List[str], urls: List[str], searxng_instance: str = "https://searx.be") -> List[str]:
    # Start with the original URLs
    all_urls = set(urls)  # Use set to avoid duplicates
    
    for query in queries:
        if not query.strip():
            continue
            
        try:
            # Prepare search parameters
            params = {
                'q': query,
                'format': 'json',
                'categories': 'general'
            }
            
            # Make request to SearXNG
            search_url = f"{searxng_instance.rstrip('/')}/search"
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; SearchBot/1.0)'}
            
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Add found URLs to the set
            if 'results' in data:
                for result in data['results'][:5]:  # Top 5 results per query
                    url = result.get('url', '')
                    if url:
                        all_urls.add(url)
            
            # Small delay between requests
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error searching for '{query}': {e}")
            continue
    
    return list(all_urls)

