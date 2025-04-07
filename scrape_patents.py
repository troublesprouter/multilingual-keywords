import requests
from bs4 import BeautifulSoup
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

def scrape_google_patents(url):
    """
    Attempts to scrape the content of a Google Patents URL using Selenium
    with explicit waits and a headed browser.

    Args:
        url (str): The URL of the Google Patents search results page.

    Returns:
        str: A string containing basic scraped information or an error message.
    """
    # Headers are less critical with Selenium but kept for reference
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    driver = None # Initialize driver to None
    try:
        print(f"Attempting to fetch URL using Selenium (Headed Browser): {url}")

        # --- Selenium Setup ---
        options = Options()
        # options.add_argument('--headless') # Removed for headed browsing
        options.add_argument('--no-sandbox') # Often needed in containerized/CI environments
        options.add_argument('--disable-dev-shm-usage') # Overcome limited resource problems
        options.add_argument(f'user-agent={headers["User-Agent"]}') # Set user agent
        options.add_argument("--window-size=1920,1080") # Specify window size
        options.add_argument("--disable-gpu") # Sometimes needed for headless

        # Assumes chromedriver executable is in the system's PATH.
        # If not, specify the path:
        # from selenium.webdriver.chrome.service import Service
        # service = Service('/path/to/chromedriver')
        # driver = webdriver.Chrome(service=service, options=options)
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 20) # Wait up to 20 seconds

        driver.get(url)

        # --- Use Explicit Wait --- 
        # Wait for the first actual result item to be VISIBLE.
        first_result_locator = (By.CSS_SELECTOR, "#resultsContainer search-result-item") 
        print(f"Waiting for element {first_result_locator} to be visible...")
        wait.until(EC.visibility_of_element_located(first_result_locator))
        print("First result item is visible. Waiting longer for potential JS rendering...")
        time.sleep(5) # Increased extra wait after element is visible
        
        page_source = driver.page_source
        print(f"Successfully fetched URL and obtained page source using Selenium.")

        if not page_source:
             return "Error: Failed to get page source using Selenium."

        # --- Parsing with BeautifulSoup (using Selenium's result) ---
        soup = BeautifulSoup(page_source, 'html.parser')

        # Get the page title
        title = soup.title.string.strip() if soup.title else "No title found"

        # Get text content - try finding a more specific container if possible,
        # otherwise fall back to body. Google Patents structure can change.
        # The explicit wait should make finding resultsContainer more reliable.
        results_container = soup.find('div', id='resultsContainer') # Example potential container
        main_content = results_container or soup.find('body')

        text_content = "No relevant text content found"
        if main_content:
            # Extract text, join parts with spaces, remove extra whitespace, take first 2000 chars
            text_content = " ".join(main_content.get_text(separator=' ', strip=True).split())[:2000] + "..."

        # --- Output ---
        output = f"""--- Scraped Content (Selenium - Headed & Explicit Wait) ---
URL: {url}
Page Title: {title}

Sample Text Content (first 2000 chars):
{text_content}
-----------------------"""
        return output

    except WebDriverException as e:
        error_message = f"Selenium WebDriver Error: {e}"
        print(error_message)
        print("Ensure WebDriver (e.g., chromedriver) is installed, compatible with your Chrome version, and in your system's PATH or specified correctly.")
        return error_message
    except Exception as e: # Catch broader exceptions including TimeoutException from wait
        error_message = f"An unexpected error occurred: {e}"
        print(error_message)
        if isinstance(e, TimeoutException):
            error_message += f" (Element {first_result_locator} did not appear within the time limit)"
        # Include info if driver was initialized, helping debug
        if driver: error_message += " (Selenium driver was active)"
        return error_message
    finally:
        # Ensure the browser is closed even if errors occur
        if driver:
            print("Closing Selenium WebDriver.")
            driver.quit()

if __name__ == "__main__":
    # The URL provided in the query
    target_url = "https://patents.google.com/?q=%E5%8F%AF%E4%BA%92%E6%8F%9B%E7%87%83%E6%96%99%E7%BB%84%E4%BB%B6"

    # Allow overriding URL via command line argument
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
        print(f"Using URL from command line argument: {target_url}")

    scraped_data = scrape_google_patents(target_url)
    
    # Write output to scrape.txt
    output_filename = "scrape.txt"
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(scraped_data)
        print(f"\nScraping results saved to {output_filename}")
    except Exception as e:
        print(f"\nError writing results to {output_filename}: {e}")

    # Print disclaimer to console
    print("\nDisclaimer:")
    print("Web scraping, especially from dynamic sites like Google Patents, can be unreliable.")
    print("The structure of the website may change, breaking the scraper.")
    print("Always respect the website's terms of service (robots.txt).")
    print("This script provides a basic example and may need significant adjustments")
    print("to reliably extract specific data points from Google Patents.")