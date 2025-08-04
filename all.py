from Queries import generate_all_queries
from Search import get_urls
from scrap1 import scrape_urls

async def company_search(user_company,product,description,client_company):
    queries=generate_all_queries(user_company,product,description,client_company)
    urls=get_urls(queries)
    await scrape_urls(urls)
    
