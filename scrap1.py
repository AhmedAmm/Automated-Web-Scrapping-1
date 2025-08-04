import asyncio
import logging
from typing import List, Optional, Dict, Any
from playwright.async_api import async_playwright, Playwright
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import trafilatura
import time
from concurrent.futures import ThreadPoolExecutor
import threading
import atexit
import signal
import sys
import requests
from urllib.parse import urlparse
import tempfile
import os
import uuid
from contextlib import asynccontextmanager

from smart_agent_conlusion import data_cleaning

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global state
_playwright_instance: Optional[Playwright] = None
_cleanup_done = False
_http_session = None

# Locks for thread safety
_playwright_lock = asyncio.Lock()
_selenium_lock = threading.Lock()

# Per-request browser instances to avoid sharing issues
_active_browsers = {}
_active_selenium_drivers = {}


class BrowserManager:
    """Manages individual browser instances to avoid sharing conflicts"""
    
    def __init__(self):
        self.browser_id = str(uuid.uuid4())
        self.browser = None
        self.context = None
        self.page = None
    
    async def __aenter__(self):
        await self.create_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
    
    async def create_browser(self):
        """Create a dedicated browser instance"""
        global _playwright_instance
        
        async with _playwright_lock:
            try:
                if _playwright_instance is None:
                    _playwright_instance = await async_playwright().start()
                
                self.browser = await _playwright_instance.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-field-trial-config',
                        '--disable-ipc-flooding-protection',
                        '--no-first-run',
                        '--no-default-browser-check',
                        '--disable-default-apps',
                        '--disable-extensions',
                        '--disable-plugins',
                        '--disable-sync',
                        '--disable-translate',
                        '--hide-scrollbars',
                        '--mute-audio',
                        '--disable-logging',
                        '--disable-gl-drawing-for-tests',
                        '--memory-pressure-off',
                        '--max_old_space_size=4096'
                    ]
                )
                
                self.context = await self.browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                
                self.page = await self.context.new_page()
                
                # Block unnecessary resources
                await self.page.route('**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}', lambda route: route.abort())
                
                _active_browsers[self.browser_id] = self
                logger.info(f"Created dedicated browser instance: {self.browser_id}")
                
            except Exception as e:
                logger.error(f"Failed to create browser {self.browser_id}: {str(e)}")
                await self.cleanup()
                raise
    
    async def cleanup(self):
        """Clean up this browser instance"""
        try:
            if self.page:
                await asyncio.wait_for(self.page.close(), timeout=3)
                self.page = None
            
            if self.context:
                await asyncio.wait_for(self.context.close(), timeout=3)
                self.context = None
            
            if self.browser:
                await asyncio.wait_for(self.browser.close(), timeout=5)
                self.browser = None
            
            if self.browser_id in _active_browsers:
                del _active_browsers[self.browser_id]
            
            logger.info(f"Cleaned up browser instance: {self.browser_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up browser {self.browser_id}: {str(e)}")


class SeleniumManager:
    """Manages individual Selenium driver instances"""
    
    def __init__(self):
        self.driver_id = str(uuid.uuid4())
        self.driver = None
    
    def __enter__(self):
        self.create_driver()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def create_driver(self):
        """Create a dedicated Selenium driver"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--disable-sync')
            chrome_options.add_argument('--disable-translate')
            chrome_options.add_argument('--hide-scrollbars')
            chrome_options.add_argument('--mute-audio')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--no-default-browser-check')
            chrome_options.add_argument('--disable-default-apps')
            chrome_options.add_argument('--memory-pressure-off')
            chrome_options.add_argument('--max_old_space_size=4096')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            
            # Prefs to disable notifications and popups
            prefs = {
                "profile.default_content_setting_values": {
                    "notifications": 2,
                    "popups": 2,
                    "geolocation": 2,
                    "media_stream": 2,
                }
            }
            chrome_options.add_experimental_option("prefs", prefs)
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(12)
            self.driver.implicitly_wait(2)
            
            _active_selenium_drivers[self.driver_id] = self
            logger.info(f"Created dedicated Selenium driver: {self.driver_id}")
            
        except Exception as e:
            logger.error(f"Failed to create Selenium driver {self.driver_id}: {str(e)}")
            self.cleanup()
            raise
    
    def cleanup(self):
        """Clean up this Selenium driver"""
        try:
            if self.driver:
                # Force quit without waiting
                try:
                    self.driver.quit()
                except:
                    # If quit fails, try to kill the process
                    try:
                        if hasattr(self.driver, 'service') and self.driver.service.process:
                            self.driver.service.process.kill()
                    except:
                        pass
                
                self.driver = None
            
            if self.driver_id in _active_selenium_drivers:
                del _active_selenium_drivers[self.driver_id]
            
            logger.info(f"Cleaned up Selenium driver: {self.driver_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up Selenium driver {self.driver_id}: {str(e)}")


def get_http_session():
    """Get or create a shared HTTP session"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    return _http_session


def is_pdf_url(url: str) -> bool:
    """Check if URL is a PDF file"""
    return url.lower().endswith('.pdf') or 'pdf' in url.lower()


async def download_pdf_content(url: str) -> Optional[str]:
    """Download PDF and extract text content"""
    try:
        session = get_http_session()
        response = session.get(url, timeout=30, stream=True)
        response.raise_for_status()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        try:
            # Try to extract text from PDF using PyPDF2
            import PyPDF2
            with open(temp_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
                
            logger.info(f"Successfully extracted PDF content from: {url}")
            return text
            
        except ImportError:
            logger.warning("PyPDF2 not installed, cannot extract PDF text")
            return None
        except Exception as e:
            logger.error(f"Failed to extract PDF content: {str(e)}")
            return None
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except:
                pass
                
    except Exception as e:
        logger.error(f"Failed to download PDF {url}: {str(e)}")
        return None


async def scrape_urls(urls: list, max_concurrent: int = 20) -> None:
    """
    Scrape multiple URLs with individual browser instances per request
    """
    try:
        # Further reduced concurrency for stability
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # Create tasks for all URLs
        tasks = [scrape_url_with_semaphore(semaphore, url) for url in urls]
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process successful results
        extraction_tasks = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to process {urls[i]}: {str(result)}")
            elif result and result.get('content'):
                # Create async task for data extraction
                task = asyncio.create_task(async_data_extraction(result, urls[i]))
                extraction_tasks.append(task)
            else:
                logger.warning(f"No content extracted from: {urls[i]}")
        
        # Wait for all data extraction tasks to complete
        if extraction_tasks:
            await asyncio.gather(*extraction_tasks, return_exceptions=True)
                
    except Exception as e:
        logger.error(f"Error in scraping pipeline: {str(e)}")
    finally:
        # Ensure cleanup of any remaining resources
        await cleanup_all()


async def scrape_url_with_semaphore(semaphore: asyncio.Semaphore, url: str) -> Optional[Dict[str, Any]]:
    """Wrapper to control concurrency with semaphore"""
    async with semaphore:
        return await scrape_url(url)


async def scrape_url(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape a single URL using dedicated browser instances
    """
    # Handle PDF files separately
    if is_pdf_url(url):
        logger.info(f"Detected PDF URL, using direct download: {url}")
        content = await download_pdf_content(url)
        if content:
            return {
                'content': content,
                'url': url,
                'method': 'pdf_download'
            }
        else:
            logger.error(f"Failed to download PDF: {url}")
            return None
    
    # Try Playwright first with dedicated browser
    try:
        async with BrowserManager() as browser_manager:
            # Navigate to URL with timeout
            await browser_manager.page.goto(url, timeout=12000, wait_until='domcontentloaded')
            
            # Minimal wait for content to load
            await browser_manager.page.wait_for_timeout(300)
            
            # Get page content
            content = await browser_manager.page.content()
            
            logger.info(f"Successfully scraped with Playwright: {url}")
            return {
                'content': content,
                'url': url,
                'method': 'playwright'
            }
    
    except Exception as e:
        logger.error(f"Playwright failed to scrape {url}: {str(e)}")
        logger.info(f"Attempting Selenium fallback for: {url}")
        
        # Try Selenium fallback with dedicated driver
        try:
            result = await asyncio.wait_for(
                selenium_scrape_with_manager(url), 
                timeout=20
            )
            if result:
                return {
                    'content': result,
                    'url': url,
                    'method': 'selenium'
                }
            else:
                return None
        except asyncio.TimeoutError:
            logger.error(f"Selenium fallback timed out for {url}")
            return None
        except Exception as selenium_error:
            logger.error(f"Selenium fallback failed for {url}: {str(selenium_error)}")
            return None


async def selenium_scrape_with_manager(url: str) -> Optional[str]:
    """Selenium scraping with dedicated driver in thread pool"""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = loop.run_in_executor(executor, selenium_scrape_fallback, url)
        return await future


def selenium_scrape_fallback(url: str) -> Optional[str]:
    """Fallback scraping function using dedicated Selenium driver"""
    try:
        with SeleniumManager() as selenium_manager:
            # Navigate to URL
            selenium_manager.driver.get(url)
            
            # Wait for page to load
            try:
                WebDriverWait(selenium_manager.driver, 3).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                logger.warning(f"Body element not found for {url}, proceeding anyway")
            
            # Minimal wait for dynamic content
            time.sleep(0.3)
            
            # Get page source
            content = selenium_manager.driver.page_source
            
        logger.info(f"Successfully scraped with Selenium fallback: {url}")
        return content
        
    except Exception as e:
        logger.error(f"Selenium fallback failed for {url}: {str(e)}")
        return None


async def async_data_extraction(scraped_data: Dict[str, Any], url: str) -> None:
    """Async wrapper for data extraction"""
    try:
        html_content = scraped_data.get('content', '')
        method = scraped_data.get('method', 'unknown')
        
        # For PDF content, skip trafilatura processing
        if method == 'pdf_download':
            text_content = html_content
            metadata = None
        else:
            # Extract main content using trafilatura
            text_content = trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=True,
                include_links=True,
                output_format='txt'
            )
            
            # Extract metadata
            metadata = trafilatura.extract_metadata(html_content)
        
        if text_content and len(text_content.strip()) > 50:  # Minimum content threshold
            # Prepare extracted data
            extracted_data = {
                'url': url,
                'content': text_content,
                'title': metadata.title if metadata else None,
                'author': metadata.author if metadata else None,
                'date': metadata.date if metadata else None,
                'description': metadata.description if metadata else None,
                'sitename': metadata.sitename if metadata else None,
                'word_count': len(text_content.split()),
                'char_count': len(text_content),
                'scraping_method': method
            }
            
            logger.info(f"Successfully extracted content from: {url} (method: {method})")
            
            # Run data_cleaning in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                await loop.run_in_executor(executor, data_cleaning, extracted_data)
            
        else:
            logger.warning(f"Insufficient content extracted from: {url}")
            
    except Exception as e:
        logger.error(f"Failed to extract content from {url}: {str(e)}")


async def cleanup_all():
    """Clean up all active browser instances"""
    global _playwright_instance, _http_session, _cleanup_done
    
    if _cleanup_done:
        return
    
    _cleanup_done = True
    logger.info("Starting cleanup of all resources...")
    
    try:
        # Clean up active browsers
        browser_cleanup_tasks = []
        for browser_manager in list(_active_browsers.values()):
            task = asyncio.create_task(browser_manager.cleanup())
            browser_cleanup_tasks.append(task)
        
        if browser_cleanup_tasks:
            await asyncio.gather(*browser_cleanup_tasks, return_exceptions=True)
        
        # Clean up active Selenium drivers
        for selenium_manager in list(_active_selenium_drivers.values()):
            selenium_manager.cleanup()
        
        # Close Playwright instance
        if _playwright_instance:
            try:
                await asyncio.wait_for(_playwright_instance.stop(), timeout=10)
                logger.info("Stopped Playwright instance")
            except Exception as e:
                logger.error(f"Error stopping Playwright: {str(e)}")
            finally:
                _playwright_instance = None
        
        # Close HTTP session
        if _http_session:
            _http_session.close()
            _http_session = None
        
        logger.info("Resource cleanup completed successfully")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")


# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    """Handle system signals for cleanup"""
    logger.info(f"Received signal {signum}, cleaning up...")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(cleanup_all())
        else:
            asyncio.run(cleanup_all())
    except Exception as e:
        logger.error(f"Error during signal cleanup: {str(e)}")
    finally:
        sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Register atexit handler for cleanup
atexit.register(lambda: asyncio.run(cleanup_all()) if not _cleanup_done else None)


# Example usage function
async def main():
    """Example usage of the improved scraper"""
    urls = [
        "https://www.cognizant.com/en_us/about/documents/2023-annual-report.pdf",
        "https://www.bbb.org/us/ny/armonk/profile/data-communication-equipment/ibm-0121-228/complaints",
        "https://www.ambitionbox.com/reviews/cognizant-reviews",
        # Add more URLs as needed
    ]
    
    await scrape_urls(urls, max_concurrent=2)


if __name__ == "__main__":
    asyncio.run(main())