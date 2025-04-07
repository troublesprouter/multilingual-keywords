import os
import google.generativeai as genai
from google.generativeai import types
import time
import re
import urllib.parse
import json
import traceback
import requests
from dotenv import load_dotenv

# Load environment variables (including GOOGLE_API_KEY and SCRAPINGDOG_API_KEY)
load_dotenv()

# Configure the API keys
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
SCRAPINGDOG_API_KEY = os.environ.get("SCRAPINGDOG_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not found.")

if not SCRAPINGDOG_API_KEY:
    print("Warning: SCRAPINGDOG_API_KEY not found. Patent scraping will fail.")

# --- Configuration ---
MODEL_NAME = "models/gemini-2.0-flash-thinking-exp-01-21"
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds
LANGUAGES = ["English", "Mandarin", "Japanese", "Korean", "German", "French", "Spanish", "Italian"]
SCRAPINGDOG_TIMEOUT = 60 # Timeout for ScrapingDog API calls

# --- Helper Function for Gemini API Calls ---

def call_gemini_with_retry(prompt, context_text=None, files=None, task_description="API call"):
    """Generic function to call Gemini API with retry logic, optionally including files."""
    if not GEMINI_API_KEY:
         return f"# Error\n\nGOOGLE_API_KEY not configured for {task_description}."

    print(f"\n--- Calling Gemini API for {task_description} ---")

    model = genai.GenerativeModel(MODEL_NAME)
    # Start with the prompt
    content_parts = [prompt]
    # Add context text if provided
    if context_text:
        if not isinstance(context_text, str):
             print(f"Warning: context_text is not a string, type: {type(context_text)}. Converting...")
             context_text = str(context_text)
        content_parts.extend(["--- CONTEXT START ---", context_text, "--- CONTEXT END ---"])
    # Add file data if provided
    files_attached_count = 0
    if files:
        if not isinstance(files, list):
             print("Warning: 'files' argument is not a list. Skipping file attachment.")
        else:
             content_parts.append("\n--- ATTACHED DOCUMENTS START ---")
             for file_data in files:
                  if isinstance(file_data, dict) and 'mime_type' in file_data and 'data' in file_data:
                       content_parts.append(file_data)
                       files_attached_count += 1
                       # Optionally log the mime_type or a placeholder for the file
                       # print(f"Attaching file with mime_type: {file_data.get('mime_type')}")
                  else:
                       print(f"Warning: Skipping invalid file data format: {file_data}")
             content_parts.append("--- ATTACHED DOCUMENTS END ---")
    print(f"Files attached: {files_attached_count}")

    # Retry mechanism
    for attempt in range(MAX_RETRIES):
        response = None
        try:
            print(f"Sending {task_description} request (Attempt {attempt + 1}/{MAX_RETRIES})...")
            start_time = time.time()
            # Use the constructed content_parts list
            response = model.generate_content(
                contents=content_parts, 
                generation_config=types.GenerationConfig(temperature=0.4),
                request_options={'timeout': 600} # Increased timeout for potentially large PDFs
            )
            elapsed_time = time.time() - start_time
            print(f"{task_description} request completed in {elapsed_time:.2f} seconds.")

            response_text = ""
            try:
                if response.candidates and response.candidates[0].content.parts:
                    response_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
                elif hasattr(response, 'parts') and response.parts:
                     response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                elif hasattr(response, 'text'):
                     response_text = response.text
            except AttributeError as e:
                 print(f"Warning: Could not extract text using standard methods. Response structure: {response}, Error: {e}")

            if response_text:
                return response_text.strip()
            else:
                 if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                     print(f"Warning: Prompt may have been blocked. Feedback: {response.prompt_feedback}")
                 elif response and hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                     print(f"Warning: Generation may have stopped. Finish Reason: {response.candidates[0].finish_reason}, Safety: {response.candidates[0].safety_ratings}")
                 else:
                      print(f"Warning: Received empty or unexpected response structure from API: {response}")

                 if attempt == MAX_RETRIES - 1:
                      return f"# Error\n\nReceived empty or problematic response from API for {task_description} after retries."
                 else:
                     print(f"Retrying {task_description} request due to empty/problematic response...")
                     time.sleep(RETRY_DELAY * (attempt + 1))
                     continue

        except Exception as e:
            print(f"Error during Gemini API {task_description} call (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            print(traceback.format_exc())
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY * (attempt + 1)} seconds...")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"Max retries reached for {task_description} API call.")
                return f"# Error\n\nAn unexpected error occurred during {task_description} after {MAX_RETRIES} attempts: {e}"

    return f"# Error\n\n{task_description} failed after retries."

# --- Scraping Functions ---

def call_scrapingdog_api(query: str, page: int):
    """Calls the ScrapingDog Google Patents API for a single query and page."""
    if not SCRAPINGDOG_API_KEY:
        print("Error: SCRAPINGDOG_API_KEY not set.")
        return {"error": "API key not configured."}

    api_endpoint = "https://api.scrapingdog.com/google_patents"
    params = {
        'api_key': SCRAPINGDOG_API_KEY,
        'query': query,
        'page': str(page)
    }
    print(f"  - Calling ScrapingDog API: Query='{query[:50]}...', Page={page}")
    try:
        response = requests.get(api_endpoint, params=params, timeout=SCRAPINGDOG_TIMEOUT)
        response.raise_for_status()
        print(f"    API response status: {response.status_code}")
        try:
            return response.json()
        except json.JSONDecodeError:
            error_message = f"ScrapingDog Error: Failed to decode JSON. Response: {response.text[:200]}..."
            print(f"    {error_message}")
            return {"error": error_message, "status_code": response.status_code}
    except requests.exceptions.Timeout:
        error_message = f"ScrapingDog Error: Request timed out for query '{query[:50]}...' page {page}."
        print(f"    {error_message}")
        return {"error": error_message}
    except requests.exceptions.HTTPError as e:
        error_message = f"ScrapingDog Error: HTTP Error {e.response.status_code} for query '{query[:50]}...' page {page}. Response: {e.response.text[:200]}..."
        print(f"    {error_message}")
        return {"error": error_message, "status_code": e.response.status_code}
    except requests.exceptions.RequestException as e:
        error_message = f"ScrapingDog Error: Request exception for query '{query[:50]}...' page {page}: {e}"
        print(f"    {error_message}")
        return {"error": error_message}
    except Exception as e:
        error_message = f"ScrapingDog Error: Unexpected error for query '{query[:50]}...' page {page}: {e}"
        print(f"    {error_message}")
        print(traceback.format_exc())
        return {"error": error_message}

def scrape_for_terms_sequentially(terms: list):
    """Scrapes patents sequentially for a list of terms (page 0 & 1 each)."""
    print(f"\n--- Starting Sequential Scraping for {len(terms)} terms ---")
    all_patents = []
    seen_patent_ids = set()
    total_api_calls = 0

    if not SCRAPINGDOG_API_KEY:
        print("Scraping skipped: SCRAPINGDOG_API_KEY not configured.")
        return [], total_api_calls

    for term in terms:
        print(f"Scraping for term: '{term}'")
        for page_num in [0, 1]:
            total_api_calls += 1
            result_data = call_scrapingdog_api(term, page_num)

            # Check for API errors in the response dict itself
            if isinstance(result_data, dict) and result_data.get("error"):
                print(f"    Skipping results for query='{term}', page={page_num} due to API error: {result_data['error']}")
                continue # Skip to next page or term

            # Process organic results
            if isinstance(result_data, dict) and result_data.get("organic_results") and isinstance(result_data["organic_results"], list):
                print(f"    Found {len(result_data['organic_results'])} results.")
                for patent in result_data["organic_results"]:
                    if isinstance(patent, dict):
                        patent_id = patent.get("patent_id")
                        if patent_id and patent_id not in seen_patent_ids:
                            # Construct URL
                            url_id_part = patent_id.replace("patent/", "")
                            url = f"https://patents.google.com/patent/{url_id_part}"
                            # Add URL to the patent dict
                            patent['url'] = url
                            all_patents.append(patent)
                            seen_patent_ids.add(patent_id)
                        elif patent_id:
                            # print(f"    Duplicate patent ID skipped: {patent_id}") # Optional: for debugging
                            pass
            else:
                print(f"    No 'organic_results' list found or unexpected format for query='{term}', page={page_num}.")
            time.sleep(0.5) # Small delay between API calls

    print(f"--- Sequential Scraping Finished --- ")
    print(f"Total ScrapingDog API calls made: {total_api_calls}")
    print(f"Total unique patents collected: {len(all_patents)}")
    return all_patents, total_api_calls

# --- Prior Art Analysis Function (Modified) ---

def format_patent_list_for_prompt(patents):
    """Formats the extracted patent data into a string for the prompt."""
    formatted_string = ""
    for i, p in enumerate(patents):
        formatted_string += f"--- Patent {i+1} ---\n"
        formatted_string += f"ID: {p.get('patent_id', 'N/A')}\n"
        # Ensure URL is present (added during scraping)
        formatted_string += f"URL: {p.get('url', 'URL Construction Failed')}\n"
        formatted_string += f"Title: {p.get('title', 'N/A')}\n"
        formatted_string += f"Publication Date: {p.get('publication_date', 'N/A')}\n"
        formatted_string += f"Assignee: {p.get('assignee', 'N/A')}\n"
        formatted_string += f"Inventor: {p.get('inventor', 'N/A')}\n"
        formatted_string += f"Snippet: {p.get('snippet', 'N/A')}\n\n"
    return formatted_string

def call_gemini_for_prior_art(description_text, concepts_descriptions_list, patents):
    """Calls the Gemini API to analyze prior art relevance based on scraped patents."""
    if not patents:
        return "\n\n## Prior Art Relevance Analysis\n\nNo patents found or provided from scraping for analysis.\n"

    concept_context = ", ".join([f"'{desc}'" for desc in concepts_descriptions_list])
    if not concept_context:
         concept_context = "(Could not parse concept descriptions)"

    formatted_patent_list = format_patent_list_for_prompt(patents)

    # Modified Prompt:
    prompt = f"""
    Act as an experienced patent examiner or prior art search specialist.
    Your task is to analyze a provided invention description against a list of patent documents.
    This list of patents was generated by searching for terms related to several of the invention's core concepts (including concepts like: {concept_context}).
    Now, evaluate these found patents for their relevance as potential prior art against the **entire invention description**.

    **Input:**
    1.  The Full Invention Description (provided in context).
    2.  List of Patent Documents (found via searches related to the invention's concepts, provided in context).

    **Instructions:**
    1.  **Analyze Description:** Carefully read the full invention description to understand its key technical features and overall inventive concept(s).
    2.  **Analyze Patents:** Review the provided patent documents (titles, snippets).
    3.  **Assess Relevance (Overall):** Evaluate how relevant each patent document is as potential prior art to the **full invention description**. Consider conceptual similarity, technical overlap, and potential anticipation or obviousness issues related to the *overall* invention.
    4.  **Identify Top Relevant:** Select the top 3-5 patents from the provided list that are most relevant to the **overall invention description**. If fewer relevant patents are found, list only those. If none are relevant, state that clearly.
    5.  **Explain Relevance (Overall):** For each selected relevant patent, provide a concise explanation (1-3 sentences) detailing *why* it is relevant to the **overall invention description** (e.g., "Discloses a power blending mechanism similar to the one described in the invention," "Describes interchangeable fuel assemblies applied to locomotives as in the invention," "Addresses autonomous control in a related context").
    6.  **Rank:** Order the selected relevant patents from most relevant to least relevant based on their relevance to the **overall invention description**.
    7.  **Format Output:** Present the results clearly in Markdown format as shown below. Include the patent ID, title, and the constructed URL for each relevant patent using standard Markdown link syntax.

    **Output Format (Strict Markdown):**

    ## Prior Art Relevance Analysis (Using Patents Found via Keyword Concepts)

    Based on the full invention description and the patents found via the keyword concepts (like {concept_context}), the following appear most relevant as potential prior art **to the overall invention**:

    **1. [Patent ID of Most Relevant Patent] - [Title of Most Relevant Patent]**
       *   **Relevance:** [Your concise explanation of why this patent is relevant to the *overall invention description*].
       *   **Link:** [[Link]]([Full Google Patents URL])

    **2. [Patent ID of Second Most Relevant Patent] - [Title of Second Most Relevant Patent]**
       *   **Relevance:** [Your concise explanation of relevance to the *overall invention description*].
       *   **Link:** [[Link]]([Full Google Patents URL])

    **(Continue listing ranked relevant patents up to 5)**

    **Note:** This analysis is based on patents retrieved using terms for various identified concepts and evaluated against the full description based on provided text. A comprehensive search requires reviewing full documents and potentially refining search strategies.

    **(If no relevant patents found, use this instead):**
    ## Prior Art Relevance Analysis (Using Patents Found via Keyword Concepts)
    Based on the provided snippets and titles, none of the patents found via the keyword concepts appear highly relevant as prior art **to the overall invention description**.

    ---

    The full invention description and the patent list follow.
    """

    # Combine description and patent list for context
    context = f"""--- INVENTION DESCRIPTION START ---
{description_text}
--- INVENTION DESCRIPTION END ---

--- PATENT LIST (Found via Keyword Concepts) START ---
{formatted_patent_list}
--- PATENT LIST (Found via Keyword Concepts) END ---
"""

    return call_gemini_with_retry(prompt, context, task_description="Overall Prior Art Analysis")


# --- Keyword Generation & Parsing ---

def call_gemini_for_keywords(prompt, description_text):
     return call_gemini_with_retry(prompt, description_text, task_description="Keyword Generation")

def parse_all_concept_data(keyword_report_md):
    """Parses the keyword report MD to find all cross-lingual concept descriptions and their terms."""
    concepts = {} # Dictionary: {concept_desc: [term1, term2, ...]} 
    try:
        # Find the start of the Cross-Lingual section
        cross_lingual_start_idx = keyword_report_md.find("### Cross-Lingual Search Concepts")
        if cross_lingual_start_idx == -1:
            print("Parsing Warning: Could not find '### Cross-Lingual Search Concepts' section.")
            return {}

        # Find the start of the next section (or end of string) to define the boundary
        language_specific_start_idx = keyword_report_md.find("### Language-Specific or Nuanced Search Terms", cross_lingual_start_idx)
        if language_specific_start_idx == -1:
             end_section_idx = len(keyword_report_md)
        else:
             end_section_idx = language_specific_start_idx

        # Extract the entire cross-lingual concepts section
        cross_lingual_section = keyword_report_md[cross_lingual_start_idx:end_section_idx]

        # Find all concept blocks within this section
        # Regex finds the description and the block of text following it until the next concept or end
        # Using (?s) for DOTALL mode so '.' matches newlines
        # Using lazy matching .*? to stop at the first lookahead assertion
        pattern = r"\*\*Concept\s*\d+:\s*([^\*]+)\*\*.*??(?=\n\s*\*\*Concept\s*\d+:|\Z)"
        matches = re.finditer(pattern, cross_lingual_section, re.DOTALL)

        found_concepts = 0
        for match in matches:
            concept_description = match.group(1).strip()
            concept_block_text = match.group(0) # The whole block including description
            # print(f"DEBUG: Found concept block for: {concept_description}")
            # print(f"DEBUG: Block text:\n{concept_block_text}\n---")
            
            # Find terms *only within this concept's block text*
            term_matches = re.findall(r"^\s*\*\s*[A-Za-z]+:\s*`([^`]+)`", concept_block_text, re.MULTILINE)
            if term_matches:
                terms = [term.strip() for term in term_matches]
                concepts[concept_description] = terms
                print(f"Parsed Concept '{concept_description}': Found {len(terms)} terms.")
                found_concepts += 1
            else:
                 print(f"Parsing Warning: Found concept '{concept_description}' but no terms matched the pattern within its block.")

        if found_concepts == 0:
             print("Parsing Warning: No concepts with terms found in the cross-lingual section.")

    except Exception as e:
        print(f"Error parsing keyword report markdown for concepts: {e}")
        print(traceback.format_exc())
        return {} # Return empty on error

    return concepts


# --- Main Report Generation Function (Modified) ---

def generate_keyword_report(description_text):
    """Generates a report with keywords, initial analysis, and deep-dive analysis."""
    print("Generating full report (Keywords -> Snippet Analysis -> PDF Deep Dive)...")
    if not description_text:
        return "# Error\n\nInvention description text is empty."

    # --- Stage 1: Keyword Generation --- 
    print("\n--- Stage 1: Generating Keywords ---")
    languages_str = ", ".join(LANGUAGES)
    # Ensure the keyword prompt itself is correctly defined here (assuming it is)
    keyword_prompt = f"""... [Existing Keyword Prompt Remains Here] ...""" # Placeholder

    keyword_report_md = call_gemini_for_keywords(keyword_prompt, description_text)

    if keyword_report_md.startswith("# Error"):
        print("Keyword generation failed. Cannot proceed.")
        return keyword_report_md

    # --- Stage 2: Scraping & Initial Analysis --- 
    print("\n--- Stage 2: Scraping & Initial Prior Art Analysis (Snippets) ---")
    prior_art_analysis_md = "\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nAnalysis could not be performed. Check logs for parsing or scraping errors.\n" # Default
    deep_dive_reports_md = "\n\n---\n\n## Detailed Prior Art Analysis (Based on Full PDFs)\n\nDeep dive analysis skipped due to errors in previous stages or lack of relevant patents found initially.\n" # Default
    top_patents_for_deep_dive = []
    scraped_patents_dict = {}
    
    # Parse ALL concepts and their terms
    all_concepts_data = parse_all_concept_data(keyword_report_md)
    all_terms_to_scrape = []
    concept_descriptions = list(all_concepts_data.keys())
    if all_concepts_data:
        for terms_list in all_concepts_data.values():
             all_terms_to_scrape.extend(terms_list)
        # Remove duplicate terms across concepts before scraping
        all_terms_to_scrape = sorted(list(set(all_terms_to_scrape)))
        print(f"Combined unique terms from all concepts for scraping: {len(all_terms_to_scrape)}")
    else:
        print("No cross-lingual concepts/terms found for scraping.")

    if all_terms_to_scrape:
        # Scrape using the combined list of unique terms
        scraped_patents_list, api_calls_made = scrape_for_terms_sequentially(all_terms_to_scrape)
        
        if scraped_patents_list:
            for p_data in scraped_patents_list:
                 if isinstance(p_data, dict) and p_data.get("patent_id"):
                      scraped_patents_dict[p_data["patent_id"]] = p_data
            
            # Call Gemini for initial analysis using ALL concept descriptions for context
            initial_analysis_md = call_gemini_for_prior_art(description_text, concept_descriptions, scraped_patents_list)
            
            if initial_analysis_md and not initial_analysis_md.startswith("# Error"):
                 prior_art_analysis_md = initial_analysis_md
                 # Parse top patents from this combined analysis
                 print("Parsing initial analysis report for top patents...")
                 top_patent_ids = re.findall(r"^\*\*\d+\.\s+((?:patent/)?\S+)\s+-", initial_analysis_md, re.MULTILINE)
                 if top_patent_ids:
                     print(f"Found {len(top_patent_ids)} top patent IDs for deep dive: {top_patent_ids}")
                     top_patents_for_deep_dive = [scraped_patents_dict[pid] for pid in top_patent_ids if pid in scraped_patents_dict]
                     print(f"Retrieved full data for {len(top_patents_for_deep_dive)} patents.")
                 else:
                     print("Could not parse top patent IDs from the initial analysis markdown.")
            else:
                 prior_art_analysis_md = f"\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nInitial analysis failed. Error: {initial_analysis_md}"
        else:
            prior_art_analysis_md = f"\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nNo patent results were found after scraping based on the terms generated for the keyword concepts.\n"
    else:
        # Handle case where no terms were parsed
        prior_art_analysis_md = "\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nCould not parse any search terms from the keyword report. Unable to perform scraping or analysis.\n"
        
    # --- Stage 3: PDF Deep Dive Analysis --- 
    print(f"\n--- Stage 3: PDF Deep Dive Analysis for {len(top_patents_for_deep_dive)} Top Patents ---")
    deep_dive_results = []
    if top_patents_for_deep_dive:
        for i, patent_data in enumerate(top_patents_for_deep_dive):
             patent_id = patent_data.get('patent_id', f'Unknown_{i+1}')
             pdf_suffix = patent_data.get('pdf')
             print(f"\nProcessing Deep Dive for: {patent_id} (PDF Suffix: {pdf_suffix})")
             
             if not pdf_suffix:
                 print("  Skipping deep dive: No PDF suffix found in scraped data.")
                 deep_dive_results.append(f"### Detailed Analysis for {patent_id}\n\nSkipped: No PDF link found in scraped data.\n")
                 continue
                 
             pdf_bytes = fetch_patent_pdf(pdf_suffix)
             if pdf_bytes:
                 analysis_md = call_gemini_for_deep_dive(description_text, patent_data, pdf_bytes)
                 deep_dive_results.append(analysis_md)
             else:
                 print(f"  Skipping deep dive for {patent_id}: Failed to fetch PDF.")
                 deep_dive_results.append(f"### Detailed Analysis for {patent_id}\n\nSkipped: Failed to download or process PDF from Google Storage.\n")
        
        if deep_dive_results:
            # Update header for clarity
            deep_dive_reports_md = "\n\n---\n\n## Detailed Prior Art Analysis (Based on Full PDFs of Top Patents)\n\n" + "\n\n---\n\n".join(deep_dive_results)

    else:
        print("Skipping deep dive analysis as no top patents were identified or retrieved from the initial analysis.")

    # --- Stage 4: Combine All Reports --- 
    print("\n--- Stage 4: Combining Reports ---")
    combined_report = keyword_report_md + "\n" + prior_art_analysis_md + "\n" + deep_dive_reports_md

    print("Finished generating combined report.")
    return combined_report


# --- Requirements Reminder (Update this manually if needed) ---
# Ensure you have installed the necessary libraries:
# pip3 install google-generativeai requests python-dotenv Flask markdown
#
# Also, create a .env file in this directory containing:
# GOOGLE_API_KEY=YOUR_GEMINI_API_KEY
# SCRAPINGDOG_API_KEY=YOUR_SCRAPINGDOG_API_KEY
# FLASK_SECRET_KEY=YOUR_FLASK_SECRET_KEY (optional, Flask will generate one)

# --- Deep Dive Analysis Functions ---

GOOGLE_PATENT_IMAGE_BASE_URL = "https://patentimages.storage.googleapis.com/"

def fetch_patent_pdf(pdf_suffix: str):
    """Downloads the patent PDF content from Google's storage."""
    if not pdf_suffix or not isinstance(pdf_suffix, str):
        print("Error: Invalid PDF suffix provided.")
        return None

    pdf_url = GOOGLE_PATENT_IMAGE_BASE_URL + pdf_suffix
    print(f"  Fetching PDF from: {pdf_url}")
    try:
        response = requests.get(pdf_url, timeout=60) # 60 second timeout for download
        response.raise_for_status()
        if 'application/pdf' in response.headers.get('Content-Type', ''):
             print(f"    Successfully fetched PDF ({len(response.content)} bytes).")
             return response.content # Return raw bytes
        else:
             print(f"    Warning: URL did not return PDF content type. URL: {pdf_url}, Content-Type: {response.headers.get('Content-Type')}")
             return None
    except requests.exceptions.Timeout:
        print(f"    Error: Timeout fetching PDF from {pdf_url}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"    Error: HTTP {e.response.status_code} fetching PDF from {pdf_url}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"    Error: Failed to fetch PDF from {pdf_url}: {e}")
        return None
    except Exception as e:
        print(f"    Error: Unexpected error fetching PDF {pdf_url}: {e}")
        return None

def call_gemini_for_deep_dive(description_text, patent_data, pdf_bytes):
    """Calls Gemini with the description and full patent PDF for detailed analysis."""
    if not pdf_bytes:
        return f"### Detailed Analysis for {patent_data.get('patent_id', 'Unknown Patent')}\n\nCould not fetch or process the PDF for detailed analysis.\n"

    patent_id = patent_data.get('patent_id', 'N/A')
    patent_title = patent_data.get('title', 'N/A')
    patent_url = patent_data.get('url', '#') # Use the already constructed URL

    prompt = f"""
    Act as an expert patent analyst performing a detailed prior art relevance assessment.

    **Input:**
    1.  The Full Invention Description (provided in context).
    2.  The Full Text of a specific Patent Document (attached PDF).

    **Task:**
    Based on a thorough review of BOTH the invention description and the attached full patent PDF, provide a detailed analysis of the patent's relevance as prior art to the invention description.

    **Output Format (Strict Markdown):**

    ### Detailed Analysis: {patent_id} - {patent_title}

    **Link:** [[Link]]({patent_url})

    **Summary of Patent:** [Provide a brief 2-4 sentence summary of the key technology disclosed in the attached patent PDF.]

    **Detailed Relevance Assessment:**
    *   [Analyze specific sections/claims/figures of the attached patent that are most relevant to the core concepts of the invention description.]
    *   [Discuss the degree of overlap or similarity between the patent's disclosure and the invention description.]
    *   [Identify key similarities and differences in the technical approaches or solutions.]
    *   [Comment on whether this patent potentially anticipates or renders obvious key aspects of the invention description.]

    **Conclusion:** [Provide a concluding statement on the overall relevance of this specific patent as prior art to the invention description, based on the full PDF review.]

    **Important:** Base your analysis **strictly** on the provided invention description and the attached full patent PDF document. Do not invent information not present in the inputs.
    """

    pdf_file_data = {
        'mime_type': 'application/pdf',
        'data': pdf_bytes
    }

    # Call the helper function, passing the PDF data in the 'files' argument
    analysis_result = call_gemini_with_retry(
        prompt,
        context_text=description_text, # Pass description as context
        files=[pdf_file_data],         # Pass PDF as file data
        task_description=f"Deep Dive Analysis for {patent_id}"
    )
    return analysis_result 