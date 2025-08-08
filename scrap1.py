# scrap1.py - Refactored Web Scraper with Enhanced JavaScript Support
import asyncio
import logging
from typing import List, Optional, Dict, Any, Tuple
from playwright.async_api import async_playwright, Playwright, Page, Browser, BrowserContext
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
import aiohttp
import re

# Import Undetected-Chromedriver and Selenium
import undetected_chromedriver as uc_selenium
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Import playwright-stealth
from playwright_stealth import stealth_async

# Import PDF extraction libraries
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import pdfminer
    from pdfminer.high_level import extract_text
except ImportError:
    pdfminer = None

from smart_agent_conlusion import data_cleaning

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Optimized browser arguments for medium-scale scraping
OPTIMIZED_BROWSER_ARGS = [
    # Essential stability arguments
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-software-rasterizer',
    
    # Memory and performance optimization
    '--disable-background-timer-throttling',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    '--memory-pressure-off',
    '--max_old_space_size=4096',
    
    # Stealth and anti-detection
    '--disable-blink-features=AutomationControlled',
    '--disable-features=VizDisplayCompositor',
    '--disable-ipc-flooding-protection',
    
    # Resource saving - MODIFIED: Only block non-essential resources
    '--blink-settings=imagesEnabled=true',  # Changed to allow images
    '--disable-extensions',
    '--disable-plugins',
    '--disable-sync',
    '--disable-translate',
    '--mute-audio',
    
    # User experience
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-default-apps',
    
    # Logging and debugging
    '--disable-logging',
    '--disable-gl-drawing-for-tests',
    '--verbose'
]

# Global state
_playwright_instance: Optional[Playwright] = None
_playwright_pool = []
_uc_selenium_pool = []
_cleanup_done = False
_http_session = None
_pools_initialized = False

# Pool size limits
PLAYWRIGHT_POOL_MAX_SIZE = 20
UC_SELENIUM_POOL_MAX_SIZE = 3

# Locks for thread safety
_playwright_lock = asyncio.Lock()
_uc_selenium_lock = asyncio.Lock()
_pools_init_lock = asyncio.Lock()

# Per-request browser instances to avoid sharing issues
_active_browsers = {}

# Common content selectors for waiting
CONTENT_SELECTORS = [
    'article', 'main', '.main-content', '#main-content', '#content', 
    '.content', '.article', '.post', '.entry-content'
]

# Timeout configurations
PAGE_LOAD_TIMEOUT = 30000  # 30 seconds for initial page load
CONTENT_WAIT_TIMEOUT = 10000  # 10 seconds for content to appear
SCROLL_DELAY = 1000  # 1 second delay after scroll
MAX_RETRIES = 2  # Maximum retry attempts


async def _is_reachable(url: str) -> bool:
    """Quick HEAD request to skip 404 / 5xx pages."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=5) as resp:
                return resp.status < 400
    except Exception:
        return False


class PlaywrightManager:
    """Manages individual Playwright browser instances with enhanced content waiting"""
    
    def __init__(self):
        self.browser_id = str(uuid.uuid4())
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    async def __aenter__(self):
        await self.create_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
    
    async def create_browser(self):
        """Create a dedicated Playwright browser instance with stealth"""
        global _playwright_instance, _playwright_pool
        
        async with _playwright_lock:
            try:
                if _playwright_instance is None:
                    _playwright_instance = await async_playwright().start()
                
                # Try to get a browser from the pool first
                if _playwright_pool:
                    self.browser = _playwright_pool.pop()
                    logger.info(f"Reused Playwright browser from pool: {self.browser_id}")
                else:
                    # Create a new browser if pool is empty
                    self.browser = await _playwright_instance.chromium.launch(
                        headless=True,
                        args=OPTIMIZED_BROWSER_ARGS
                    )
                    logger.info(f"Created new Playwright browser: {self.browser_id}")
                
                # Create a new context and page for this request
                self.context = await self.browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    java_script_enabled=True
                )
                
                self.page = await self.context.new_page()
                
                # Apply playwright-stealth for enhanced stealth
                await stealth_async(self.page)
                logger.info(f"Applied playwright-stealth to browser: {self.browser_id}")
                
                # MODIFIED: Only block non-essential resources (ads, trackers)
                await self._setup_resource_blocking()
                
                _active_browsers[self.browser_id] = self
                logger.info(f"Created dedicated Playwright browser with enhanced content waiting: {self.browser_id}")
                
            except Exception as e:
                logger.error(f"Failed to create Playwright browser {self.browser_id}: {str(e)}")
                await self.cleanup()
                raise
    
    async def _setup_resource_blocking(self):
        """Set up resource blocking - only block ads and trackers, not essential resources"""
        if not self.page:
            return
            
        # Block common ad and tracking domains
        ad_domains = [
            'doubleclick.net', 'googlesyndication.com', 'googletagmanager.com',
            'google-analytics.com', 'facebook.com/tr', 'facebook.net',
            'amazon-adsystem.com', 'adnxs.com', 'rubiconproject.com'
        ]
        
        # Block large media files but allow essential resources
        await self.page.route('**/*.{png,jpg,jpeg,gif,svg,webp,mp4,webm,avi,mov}', lambda route: route.abort())
        
        # Block ads by domain
        async def block_ads(route):
            url = route.request.url
            if any(domain in url for domain in ad_domains):
                await route.abort()
            else:
                await route.continue_()
        
        await self.page.route('**/*', block_ads)
    
    async def wait_for_content(self, url: str, retry_count: int = 0) -> bool:
        """Wait for content to load with retry logic"""
        if not self.page:
            return False
            
        try:
            # Navigate to URL with increased timeout
            await self.page.goto(url, timeout=PAGE_LOAD_TIMEOUT, wait_until='domcontentloaded')
            
            # First try waiting for network idle
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
                logger.info(f"Network idle reached for {url}")
            except:
                logger.info(f"Network idle timeout for {url}, continuing with content checks")
            
            # Try to find content using common selectors
            content_found = False
            
            for selector in CONTENT_SELECTORS:
                try:
                    # Wait for the selector to appear
                    await self.page.wait_for_selector(selector, timeout=2000)
                    logger.info(f"Found content using selector: {selector}")
                    content_found = True
                    break
                except:
                    continue
            
            # If no content selector found, try waiting for any text content
            if not content_found:
                try:
                    # Check if page has substantial text content
                    text_content = await self.page.evaluate('document.body.innerText.length')
                    if text_content > 500:  # Arbitrary threshold for "substantial" content
                        content_found = True
                        logger.info(f"Found substantial text content ({text_content} chars)")
                except:
                    pass
            
            # If still no content, try scrolling to trigger lazy loading
            if not content_found:
                logger.info(f"No content found initially, attempting to scroll for {url}")
                await self._scroll_page()
                
                # Check again after scrolling
                for selector in CONTENT_SELECTORS:
                    try:
                        await self.page.wait_for_selector(selector, timeout=2000)
                        logger.info(f"Found content after scrolling using selector: {selector}")
                        content_found = True
                        break
                    except:
                        continue
                
                # If still no content selector, check text content again
                if not content_found:
                    try:
                        text_content = await self.page.evaluate('document.body.innerText.length')
                        if text_content > 500:
                            content_found = True
                            logger.info(f"Found substantial text content after scrolling ({text_content} chars)")
                    except:
                        pass
            
            return content_found
            
        except Exception as e:
            logger.error(f"Error waiting for content (attempt {retry_count + 1}): {str(e)}")
            
            # Retry if we haven't reached max retries
            if retry_count < MAX_RETRIES:
                logger.info(f"Retrying content load for {url} (attempt {retry_count + 2})")
                await asyncio.sleep(1)  # Wait before retry
                return await self.wait_for_content(url, retry_count + 1)
            
            return False
    
    async def _scroll_page(self):
        """Scroll the page to trigger lazy loading"""
        if not self.page:
            return
            
        try:
            # Scroll to bottom in increments
            for i in range(3):
                await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(SCROLL_DELAY / 1000)  # Convert to seconds
            
            # Scroll back to top
            await self.page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(SCROLL_DELAY / 1000)
            
            logger.info("Page scrolling completed")
        except Exception as e:
            logger.error(f"Error during page scrolling: {str(e)}")
    
    async def get_page_content(self) -> str:
        """Get the full page content after JavaScript execution"""
        if not self.page:
            return ""
            
        try:
            # MODIFIED: Use documentElement.outerHTML for complete DOM capture
            content = await self.page.evaluate('document.documentElement.outerHTML')
            return content
        except Exception as e:
            logger.error(f"Error getting page content: {str(e)}")
            return ""
    
    async def cleanup(self):
        """Clean up this Playwright browser instance"""
        try:
            if self.page:
                await asyncio.wait_for(self.page.close(), timeout=3)
                self.page = None
            
            if self.context:
                await asyncio.wait_for(self.context.close(), timeout=3)
                self.context = None
            
            if self.browser:
                # Return browser to pool instead of closing it
                global _playwright_pool
                if len(_playwright_pool) < PLAYWRIGHT_POOL_MAX_SIZE:
                    _playwright_pool.append(self.browser)
                    logger.info(f"Returned Playwright browser to pool: {self.browser_id}")
                else:
                    await asyncio.wait_for(self.browser.close(), timeout=5)
                    logger.info(f"Closed excess Playwright browser: {self.browser_id}")
                self.browser = None
            
            if self.browser_id in _active_browsers:
                del _active_browsers[self.browser_id]
            
            logger.info(f"Cleaned up Playwright browser: {self.browser_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up Playwright browser {self.browser_id}: {str(e)}")


class UC_SeleniumManager:
    """Manages individual Undetected-Chromedriver browser instances with enhanced content waiting"""
    
    def __init__(self):
        self.browser_id = str(uuid.uuid4())
        self.driver = None
    
    async def __aenter__(self):
        await self.create_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
    
    async def create_browser(self):
        """Create a dedicated Undetected-Chromedriver browser instance"""
        global _uc_selenium_pool
        
        async with _uc_selenium_lock:
            try:
                # Try to get a driver from the pool first
                if _uc_selenium_pool:
                    self.driver = _uc_selenium_pool.pop()
                    logger.info(f"Reused Undetected-Chromedriver from pool: {self.browser_id}")
                else:
                    # Create a new driver if pool is empty
                    # Run in executor to avoid blocking the event loop
                    loop = asyncio.get_event_loop()
                    self.driver = await loop.run_in_executor(
                        None, 
                        self._create_driver_sync
                    )
                    logger.info(f"Created new Undetected-Chromedriver: {self.browser_id}")
                
                _active_browsers[self.browser_id] = self
                
            except Exception as e:
                logger.error(f"Failed to create Undetected-Chromedriver {self.browser_id}: {str(e)}")
                await self.cleanup()
                raise
    
    def _create_driver_sync(self):
        """Synchronous method to create the driver (run in executor)"""
        chrome_options = Options()
        
        # Add all optimized browser arguments
        for arg in OPTIMIZED_BROWSER_ARGS + ['--headless']:
            chrome_options.add_argument(arg)
        
        # Create undetected chromedriver
        driver = uc_selenium.Chrome(options=chrome_options)
        
        # Set page load timeout
        driver.set_page_load_timeout(30)
        
        return driver
    
    async def wait_for_content(self, url: str, retry_count: int = 0) -> bool:
        """Wait for content to load with retry logic"""
        if not self.driver:
            return False
            
        try:
            # Navigate to URL
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.driver.get, url)
            
            # First wait for body to be present
            wait = WebDriverWait(self.driver, 10)
            await loop.run_in_executor(
                None, 
                wait.until, 
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Try to find content using common selectors
            content_found = False
            
            for selector in CONTENT_SELECTORS:
                try:
                    # Wait for the selector to appear
                    element = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if element:
                        logger.info(f"Found content using selector: {selector}")
                        content_found = True
                        break
                except:
                    continue
            
            # If no content selector found, try waiting for any text content
            if not content_found:
                try:
                    # Check if page has substantial text content
                    text_content = await loop.run_in_executor(
                        None, 
                        lambda: self.driver.find_element(By.TAG_NAME, "body").text
                    )
                    if len(text_content) > 500:  # Arbitrary threshold for "substantial" content
                        content_found = True
                        logger.info(f"Found substantial text content ({len(text_content)} chars)")
                except:
                    pass
            
            # If still no content, try scrolling to trigger lazy loading
            if not content_found:
                logger.info(f"No content found initially, attempting to scroll for {url}")
                await self._scroll_page()
                
                # Check again after scrolling
                for selector in CONTENT_SELECTORS:
                    try:
                        element = wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        if element:
                            logger.info(f"Found content after scrolling using selector: {selector}")
                            content_found = True
                            break
                    except:
                        continue
                
                # If still no content selector, check text content again
                if not content_found:
                    try:
                        text_content = await loop.run_in_executor(
                            None, 
                            lambda: self.driver.find_element(By.TAG_NAME, "body").text
                        )
                        if len(text_content) > 500:
                            content_found = True
                            logger.info(f"Found substantial text content after scrolling ({len(text_content)} chars)")
                    except:
                        pass
            
            return content_found
            
        except Exception as e:
            logger.error(f"Error waiting for content (attempt {retry_count + 1}): {str(e)}")
            
            # Retry if we haven't reached max retries
            if retry_count < MAX_RETRIES:
                logger.info(f"Retrying content load for {url} (attempt {retry_count + 2})")
                await asyncio.sleep(1)  # Wait before retry
                return await self.wait_for_content(url, retry_count + 1)
            
            return False
    
    async def _scroll_page(self):
        """Scroll the page to trigger lazy loading"""
        if not self.driver:
            return
            
        try:
            # Scroll to bottom in increments
            loop = asyncio.get_event_loop()
            for _ in range(3):
                await loop.run_in_executor(
                    None,
                    lambda: self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                )
                await asyncio.sleep(SCROLL_DELAY / 1000)  # Convert to seconds
            
            # Scroll back to top
            await loop.run_in_executor(
                None,
                lambda: self.driver.execute_script("window.scrollTo(0, 0);")
            )
            await asyncio.sleep(SCROLL_DELAY / 1000)
            
            logger.info("Page scrolling completed")
        except Exception as e:
            logger.error(f"Error during page scrolling: {str(e)}")
    
    async def get_page_content(self) -> str:
        """Get the full page source after JavaScript execution"""
        if not self.driver:
            return ""
            
        try:
            # Get page source
            loop = asyncio.get_event_loop()
            page_source = await loop.run_in_executor(None, lambda: self.driver.page_source)
            return page_source
        except Exception as e:
            logger.error(f"Error getting page content: {str(e)}")
            return ""
    
    async def cleanup(self):
        """Clean up this Undetected-Chromedriver instance"""
        try:
            if self.driver:
                # Return driver to pool instead of closing it
                global _uc_selenium_pool
                if len(_uc_selenium_pool) < UC_SELENIUM_POOL_MAX_SIZE:
                    _uc_selenium_pool.append(self.driver)
                    logger.info(f"Returned Undetected-Chromedriver to pool: {self.browser_id}")
                else:
                    # Run in executor to avoid blocking the event loop
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.driver.quit)
                    logger.info(f"Closed excess Undetected-Chromedriver: {self.browser_id}")
                self.driver = None
            
            if self.browser_id in _active_browsers:
                del _active_browsers[self.browser_id]
            
            logger.info(f"Cleaned up Undetected-Chromedriver: {self.browser_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up Undetected-Chromedriver {self.browser_id}: {str(e)}")


def get_http_session():
    """Get or create a shared HTTP session"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        _http_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    return _http_session


def is_pdf_url(url: str, content_type: Optional[str] = None) -> bool:
    """Check if URL is a PDF file based on URL or content type"""
    # Check URL
    url_check = url.lower().endswith('.pdf') or 'pdf' in url.lower()
    
    # Check content type if provided
    content_type_check = content_type and 'application/pdf' in content_type.lower()
    
    return url_check or content_type_check


async def download_pdf_content(url: str) -> Optional[str]:
    """Download PDF and extract text content with multiple fallback methods"""
    try:
        session = get_http_session()
        
        # Make a HEAD request first to check content type
        head_response = session.head(url, timeout=10)
        content_type = head_response.headers.get('Content-Type', '')
        
        # If it's not a PDF based on content type, return None
        if not is_pdf_url(url, content_type):
            logger.warning(f"URL does not appear to be a PDF: {url}")
            return None
        
        # Download the PDF
        response = session.get(url, timeout=30, stream=True)
        response.raise_for_status()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        try:
            # Try to extract text using PyPDF2 first
            if PyPDF2:
                try:
                    with open(temp_path, 'rb') as file:
                        pdf_reader = PyPDF2.PdfReader(file)
                        text = ""
                        for page in pdf_reader.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text
                        
                        if text.strip():
                            logger.info(f"Successfully extracted PDF content using PyPDF2 from: {url}")
                            return text
                except Exception as e:
                    logger.warning(f"PyPDF2 extraction failed: {str(e)}")
            
            # Fallback to pdfminer.six if available
            if pdfminer:
                try:
                    text = extract_text(temp_path)
                    if text.strip():
                        logger.info(f"Successfully extracted PDF content using pdfminer from: {url}")
                        return text
                except Exception as e:
                    logger.warning(f"pdfminer extraction failed: {str(e)}")
            
            # If both methods failed
            logger.error(f"Failed to extract PDF content from: {url}")
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


async def initialize_pools():
    """Initialize all browser pools in a thread-safe manner"""
    global _pools_initialized, _pools_init_lock
    
    if _pools_initialized:
        return
    
    async with _pools_init_lock:
        if _pools_initialized:
            return  # Double-check pattern
            
        logger.info("Initializing browser pools...")
        
        # Initialize Playwright pool
        await initialize_playwright_pool(pool_size=20)
        
        # Initialize Undetected-Chromedriver pool
        await initialize_uc_selenium_pool(pool_size=3)
        
        _pools_initialized = True
        logger.info("All browser pools initialized successfully")


async def initialize_playwright_pool(pool_size: int = 20):
    """Initialize the Playwright browser pool"""
    global _playwright_pool, _playwright_instance
    
    if _playwright_pool:
        return  # Pool already initialized
    
    logger.info(f"Initializing Playwright pool with {pool_size} browsers...")
    
    if _playwright_instance is None:
        _playwright_instance = await async_playwright().start()
    
    for _ in range(pool_size):
        try:
            browser = await _playwright_instance.chromium.launch(
                headless=True,
                args=OPTIMIZED_BROWSER_ARGS
            )
            _playwright_pool.append(browser)
            logger.info(f"Added browser to Playwright pool, current size: {len(_playwright_pool)}")
        except Exception as e:
            logger.error(f"Failed to create Playwright browser for pool: {str(e)}")
    
    logger.info(f"Playwright pool initialized with {len(_playwright_pool)} browsers")


async def initialize_uc_selenium_pool(pool_size: int = 3):
    """Initialize the Undetected-Chromedriver pool"""
    global _uc_selenium_pool
    
    if _uc_selenium_pool:
        return  # Pool already initialized
    
    logger.info(f"Initializing Undetected-Chromedriver pool with {pool_size} browsers...")
    
    for _ in range(pool_size):
        try:
            # Create driver in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            chrome_options = Options()
            
            # Add all optimized browser arguments
            for arg in OPTIMIZED_BROWSER_ARGS + ['--headless']:
                chrome_options.add_argument(arg)
            
            driver = await loop.run_in_executor(
                None, 
                lambda: uc_selenium.Chrome(options=chrome_options)
            )
            
            # Set page load timeout
            await loop.run_in_executor(None, driver.set_page_load_timeout, 30)
            
            _uc_selenium_pool.append(driver)
            logger.info(f"Added browser to Undetected-Chromedriver pool, current size: {len(_uc_selenium_pool)}")
        except Exception as e:
            logger.error(f"Failed to create Undetected-Chromedriver for pool: {str(e)}")
    
    logger.info(f"Undetected-Chromedriver pool initialized with {len(_uc_selenium_pool)} browsers")


async def scrape_urls(urls: list, max_concurrent: int = 20) -> None:
    """
    Scrape multiple URLs with individual browser instances per request
    """
    try:
        # Initialize all browser pools with increased sizes
        await initialize_pools()
        
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
    Scrape a single URL using Playwright as main and Undetected-Chromedriver as fallback
    with enhanced content waiting and retry logic
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
        
    if not await _is_reachable(url):
        logger.warning(f"Skipping unreachable URL: {url}")
        return None

    # Try Playwright Stealth first with dedicated browser
    try:
        async with PlaywrightManager() as playwright_manager:
            # Wait for content to load with retry logic
            content_loaded = await playwright_manager.wait_for_content(url)
            
            if content_loaded:
                # Get page content after JavaScript execution
                content = await playwright_manager.get_page_content()
                
                logger.info(f"Successfully scraped with Playwright Stealth: {url}")
                return {
                    'content': content,
                    'url': url,
                    'method': 'playwright_stealth'
                }
            else:
                logger.warning(f"Content loading failed with Playwright for: {url}")
                raise Exception("Content loading failed")
    
    except Exception as e:
        logger.error(f"Playwright Stealth failed to scrape {url}: {str(e)}")
        logger.info(f"Attempting Undetected-Chromedriver fallback for: {url}")
        
        # Try Undetected-Chromedriver as fallback
        try:
            async with UC_SeleniumManager() as uc_selenium_manager:
                # Wait for content to load with retry logic
                content_loaded = await uc_selenium_manager.wait_for_content(url)
                
                if content_loaded:
                    # Get page content after JavaScript execution
                    content = await uc_selenium_manager.get_page_content()
                    
                    logger.info(f"Successfully scraped with Undetected-Chromedriver: {url}")
                    return {
                        'content': content,
                        'url': url,
                        'method': 'undetected_chromedriver'
                    }
                else:
                    logger.warning(f"Content loading failed with Undetected-Chromedriver for: {url}")
                    raise Exception("Content loading failed")
            
        except Exception as e:
            logger.error(f"Undetected-Chromedriver failed to scrape {url}: {str(e)}")
            return None


async def async_data_extraction(scraped_data: Dict[str, Any], url: str) -> None:
    """Async wrapper for data extraction using trafilatura"""
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
            ) or "" 
            
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
    global _playwright_instance, _playwright_pool, _uc_selenium_pool, _http_session, _cleanup_done
    
    if _cleanup_done:
        return
    
    _cleanup_done = True
    logger.info("Starting cleanup of all resources...")
    
    try:
        # Clean up Playwright pool
        if _playwright_pool:
            logger.info(f"Cleaning up {len(_playwright_pool)} Playwright browsers...")
            for browser in _playwright_pool:
                try:
                    await browser.close()
                except Exception as e:
                    logger.error(f"Error closing Playwright browser: {str(e)}")
            _playwright_pool.clear()
            logger.info("Playwright pool cleaned up")
        
        # Clean up Undetected-Chromedriver pool
        if _uc_selenium_pool:
            logger.info(f"Cleaning up {len(_uc_selenium_pool)} Undetected-Chromedriver instances...")
            loop = asyncio.get_event_loop()
            for driver in _uc_selenium_pool:
                try:
                    await loop.run_in_executor(None, driver.quit)
                except Exception as e:
                    logger.error(f"Error closing Undetected-Chromedriver: {str(e)}")
            _uc_selenium_pool.clear()
            logger.info("Undetected-Chromedriver pool cleaned up")
        
        # Clean up active browsers
        browser_cleanup_tasks = []
        for browser_manager in list(_active_browsers.values()):
            task = asyncio.create_task(browser_manager.cleanup())
            browser_cleanup_tasks.append(task)
        
        if browser_cleanup_tasks:
            await asyncio.gather(*browser_cleanup_tasks, return_exceptions=True)
        
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
    
    await scrape_urls(urls, max_concurrent=20)


if __name__ == "__main__":
    asyncio.run(main())