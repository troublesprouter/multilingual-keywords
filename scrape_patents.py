import requests
import sys
import os
import json # Added for JSON handling
import traceback
from dotenv import load_dotenv # Added for .env handling

# --- Removed Selenium and Playwright Imports ---


def scrape_google_patents_api(api_key: str, query: str, page: int = 0):
    """
    Scrapes Google Patents using the ScrapingDog API.

    Args:
        api_key (str): Your ScrapingDog API key.
        query (str): The search query.
        page (int): The results page number (0-indexed).

    Returns:
        dict or str: The parsed JSON response from the API or an error message string.
    """
    api_endpoint = "https://api.scrapingdog.com/google_patents"
    params = {
        'api_key': api_key,
        'query': query,
        'page': str(page) # API expects page as string
        # Add other parameters here if needed, e.g., 'num': '20'
    }

    print(f"Attempting API request for query='{query}', page={page}")

    try:
        response = requests.get(api_endpoint, params=params, timeout=60) # Added timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        print(f"API request successful (Status: {response.status_code})")
        try:
            # Attempt to parse JSON
            data = response.json()
            return data
        except json.JSONDecodeError:
            error_message = f"API Error: Failed to decode JSON response. Response text: {response.text[:500]}..."
            print(error_message)
            return {"error": error_message, "status_code": response.status_code}

    except requests.exceptions.Timeout:
        error_message = f"API Error: Request timed out for page {page}."
        print(error_message)
        return {"error": error_message}
    except requests.exceptions.HTTPError as e:
        error_message = f"API Error: HTTP Error: {e.response.status_code} {e.response.reason} for page {page}. Response: {e.response.text[:500]}..."
        print(error_message)
        return {"error": error_message, "status_code": e.response.status_code}
    except requests.exceptions.RequestException as e:
        error_message = f"API Error: A request exception occurred for page {page}: {e}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:
        error_message = f"An unexpected error occurred during API call for page {page}: {e}\n{traceback.format_exc()}"
        print(error_message)
        return {"error": error_message}

if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    api_key = os.getenv("SCRAPINGDOG_API_KEY")

    if not api_key:
        print("Error: SCRAPINGDOG_API_KEY not found in environment variables or .env file.")
        print("Please create a .env file in the same directory as the script with:")
        print("SCRAPINGDOG_API_KEY=YOUR_API_KEY")
        sys.exit(1)

    # Patent query
    patent_query = "可互换燃料组件"

    # Allow overriding the query via command line argument (optional)
    if len(sys.argv) > 1:
        patent_query = sys.argv[1]
        print(f"Using query from command line argument: {patent_query}")

    # Define the pages to scrape
    pages_to_scrape = [0, 1]

    all_results_data = {}

    # --- Execute the scrape using ScrapingDog API ---
    print(f"\nStarting scrape using ScrapingDog API for query: '{patent_query}'")
    for page_num in pages_to_scrape:
        print(f"\n--- Scraping Page {page_num} ---")
        result_data = scrape_google_patents_api(api_key, patent_query, page=page_num)
        all_results_data[f"page_{page_num}"] = result_data
        print("-" * 20)

    # --- Output Combined JSON Results ---
    output_filename = "scrape.txt"
    print(f"\n--- All Scraping Attempts Completed ---")
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            # Write the combined results as a single JSON object
            json.dump(all_results_data, f, ensure_ascii=False, indent=4)
        print(f"Combined scraping results saved as JSON to {output_filename}")
    except Exception as e:
        print(f"\nError writing combined JSON results to {output_filename}: {e}")

    # Optional: Print summary or confirmation to console
    print("\n--- Results Summary (Saved to scrape.txt) ---")
    if f"page_0" in all_results_data and isinstance(all_results_data["page_0"], dict) and "organic_results" in all_results_data["page_0"]:
         print(f"Page 0: Found {len(all_results_data['page_0']['organic_results'])} organic results.")
    elif f"page_0" in all_results_data and isinstance(all_results_data["page_0"], dict) and "error" in all_results_data["page_0"]:
         print(f"Page 0: Error - {all_results_data['page_0']['error']}")
    else:
         print("Page 0: No results or unexpected format.")

    if f"page_1" in all_results_data and isinstance(all_results_data["page_1"], dict) and "organic_results" in all_results_data["page_1"]:
         print(f"Page 1: Found {len(all_results_data['page_1']['organic_results'])} organic results.")
    elif f"page_1" in all_results_data and isinstance(all_results_data["page_1"], dict) and "error" in all_results_data["page_1"]:
         print(f"Page 1: Error - {all_results_data['page_1']['error']}")
    else:
         print("Page 1: No results or unexpected format.")


    # Print disclaimer
    print("\nDisclaimer:")
    print("This script uses the ScrapingDog API to fetch Google Patents data.")
    print("Ensure you have sufficient API credits.")
    print("Refer to ScrapingDog documentation for API usage details and terms.")

# --- Requirements Reminder ---
# Ensure you have installed the necessary libraries:
# pip3 install requests python-dotenv
#
# Also, create a .env file in this directory containing:
# SCRAPINGDOG_API_KEY=YOUR_API_KEY