from Queries import generate_product_competitor_queries
from Search import get_urls
from scrap1 import scrape_urls

async def company_search(product,description):
    queries=generate_product_competitor_queries(product,description)
    urls=get_urls(queries)
    await scrape_urls(urls)
    
