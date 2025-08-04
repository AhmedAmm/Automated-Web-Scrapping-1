from Queries import generate_client_profile_queries
from Search import get_urls
from scrap1 import scrape_urls

async def company_search(client):
    queries=generate_client_profile_queries(client)
    urls=get_urls(queries)
    await scrape_urls(urls)
    
