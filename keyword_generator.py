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
from collections import defaultdict
import concurrent.futures # Added for concurrency

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
# MODEL_NAME = "models/gemini-2.5-pro-preview-03-25"
# MODEL_NAME = "models/gemini-2.0-flash"
# MODEL_NAME = "models/gemini-2.0-flash-lite"

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

def call_scrapingdog_api(query: str, page: int, num: str = '10'):
    """Calls the ScrapingDog Google Patents API for a single query and page with retries."""
    if not SCRAPINGDOG_API_KEY:
        print("Error: SCRAPINGDOG_API_KEY not set.")
        return {"error": "API key not configured."}

    api_endpoint = "https://api.scrapingdog.com/google_patents"
    params = {
        'api_key': SCRAPINGDOG_API_KEY,
        'query': query,
        'page': str(page),
        'num': num
    }
    print(f"  - Calling ScrapingDog API: Query='{query[:50]}...', Page={page}")

    # --- Retry Logic --- 
    for attempt in range(MAX_RETRIES):
        error_message = None
        try:
            response = requests.get(api_endpoint, params=params, timeout=SCRAPINGDOG_TIMEOUT)
            response.raise_for_status()
            print(f"    API response status: {response.status_code} (Attempt {attempt + 1}/{MAX_RETRIES})")
            try:
                return response.json()
            except json.JSONDecodeError:
                error_message = f"ScrapingDog Error: Failed to decode JSON. Response: {response.text[:200]}..."
                print(f"    {error_message}")
                if attempt < MAX_RETRIES - 1:
                     print(f"    Retrying due to JSON decode error...")
                     time.sleep(RETRY_DELAY * (attempt + 1))
                     continue
                else:
                    return {"error": error_message, "status_code": response.status_code}

        except requests.exceptions.Timeout:
            error_message = f"ScrapingDog Error: Request timed out for Query='{query[:50]}...', Page={page}."
            print(f"    {error_message} (Attempt {attempt + 1}/{MAX_RETRIES})")
        except requests.exceptions.RequestException as e:
            error_message = f"ScrapingDog Error: Request exception for Query='{query[:50]}...', Page={page}: {e}"
            print(f"    {error_message} (Attempt {attempt + 1}/{MAX_RETRIES})")
            is_400_error = False
            if hasattr(e, 'response') and e.response is not None and hasattr(e.response, 'status_code') and e.response.status_code == 400:
                 is_400_error = True
                 return {"error": error_message, "status_code": 400}
            if 500 <= e.response.status_code < 600 and attempt < MAX_RETRIES - 1:
                print(f"    Retrying due to server error...")
            else:
                return {"error": error_message, "status_code": e.response.status_code}

        if error_message and attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAY * (attempt + 1)
            print(f"    Retrying in {delay} seconds...")
            time.sleep(delay)
        elif error_message:
             print(f"    Max retries reached for Query='{query[:50]}...', Page={page}. Returning error.")
             return {"error": error_message}
            
    return {"error": "Scraping failed after retries, unknown state."}

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

def call_gemini_for_prior_art(description_text, concepts_descriptions_list, patents, focus_area=None):
    """Calls the Gemini API to analyze prior art relevance based on scraped patents, considering a focus area."""
    if not patents:
        return "\n\n## Prior Art Relevance Analysis\n\nNo patents found or provided from scraping for analysis.\n"

    concept_context = ", ".join([f"'{desc}'" for desc in concepts_descriptions_list])
    if not concept_context:
         concept_context = "(Could not parse concept descriptions)"

    formatted_patent_list = format_patent_list_for_prompt(patents)

    # Add focus area instruction if provided
    focus_instruction = ""
    if focus_area:
        focus_instruction = f"\n**User Focus Area:** The user is particularly interested in aspects related to: '{focus_area}'. Please prioritize relevance related to this focus when analyzing and ranking patents. If the focus area suggests excluding certain aspects, please adhere to that."

    # --- Restore Full Prompt --- 
    prompt = f"""
    Act as an experienced patent examiner or prior art search specialist.
    Your task is to analyze a provided invention description against a list of patent documents.{focus_instruction}
    This list of patents was generated by searching for terms related to several of the invention's core concepts (including concepts like: {concept_context}).
    Now, evaluate these found patents for their relevance as potential prior art against the **entire invention description**, paying close attention to the specified user focus area if provided.

    **Input:**
    1.  The Full Invention Description (provided in context).
    2.  List of Patent Documents (found via searches related to the invention's concepts, provided in context).
    3.  User Focus Area (if specified above).

    **Instructions:**
    1.  **Analyze Description:** Carefully read the full invention description to understand its key technical features and overall inventive concept(s), keeping the user's focus area in mind.
    2.  **Analyze Patents:** Review the provided patent documents (titles, snippets), focusing on aspects relevant to the user's focus area.
    3.  **Assess Relevance (Overall):** Evaluate how relevant each patent document is as potential prior art to the **full invention description**, prioritizing the user's focus area. Consider conceptual similarity, technical overlap, and potential anticipation or obviousness issues.
    4.  **Identify Relevant Patents:** Select the patents from the provided list that are most relevant to the **overall invention description**, according to the user's focus area.
    5.  **Explain Relevance (Overall):** For each selected relevant patent, provide a concise explanation (1-3 sentences) detailing *why* it is relevant to the **overall invention description**, highlighting aspects related to the user's focus area.
    6.  **Rank:** Order the selected relevant patents from most relevant to least relevant based on their relevance to the **overall invention description** and the user's focus area.
    7.  **Format Output:** Present the results clearly in Markdown format as shown below. Include the patent ID, title, and the constructed URL for each relevant patent using standard Markdown link syntax.

    **Output Format (Strict Markdown):**

    ## Prior Art Relevance Analysis (Using Patents Found via Keyword Concepts)

    Based on the full invention description, the user focus area ('{focus_area if focus_area else 'General'}'), and the patents found via the keyword concepts (like {concept_context}), the following appear most relevant as potential prior art **to the overall invention**:

    **1. [Patent ID of Most Relevant Patent] - [Title of Most Relevant Patent]**
       *   **Relevance:** [Your concise explanation of relevance, emphasizing focus area].
       *   **Link:** [[Link]]([Full Google Patents URL])

    **2. [Patent ID of Second Most Relevant Patent] - [Title of Second Most Relevant Patent]**
       *   **Relevance:** [Your concise explanation of relevance, emphasizing focus area].
       *   **Link:** [[Link]]([Full Google Patents URL])

    **(Continue listing ranked relevant patents)**

    **Note:** This analysis is based on patents retrieved using terms for various identified concepts and evaluated against the full description based on provided text and user focus. A comprehensive search requires reviewing full documents and potentially refining search strategies.

    **(If no relevant patents found, use this instead):**
    ## Prior Art Relevance Analysis (Using Patents Found via Keyword Concepts)
    Based on the provided snippets, titles, and user focus ('{focus_area if focus_area else 'General'}'), none of the patents found via the keyword concepts appear highly relevant as prior art **to the overall invention description**.

    ---

    The full invention description and the patent list follow.
    """

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
    """Parses the keyword report MD to find all cross-lingual concept descriptions and their terms, structured by language."""
    concepts = {} # Dictionary: {concept_desc: {language: [terms]}}
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
        # Corrected lazy matching to stop at the first lookahead assertion
        pattern = r"\*\*Concept\s*\d+:\s*([^\*]+)\*\*.*?(?=\n\s*\*\*Concept\s*\d+:|\Z)"
        matches = re.finditer(pattern, cross_lingual_section, re.DOTALL)

        found_concepts = 0
        for match in matches:
            concept_description = match.group(1).strip()
            concept_block_text = match.group(0)
            
            language_terms = defaultdict(list) # Use defaultdict for easier appending
            # Find language lines and the terms within them
            # Regex captures the Language and the comma-separated terms inside backticks
            lang_term_matches = re.findall(r"^\s*\*\s*([A-Za-z]+):\s*`([^`]+)`", concept_block_text, re.MULTILINE)
            
            if lang_term_matches:
                for lang, terms_str in lang_term_matches:
                    # Split comma-separated terms and strip whitespace
                    terms = [term.strip() for term in terms_str.split(',') if term.strip()]
                    if terms:
                        language_terms[lang.strip()] = terms
                        
                if language_terms:
                    concepts[concept_description] = dict(language_terms) # Convert back to regular dict for output
                    print(f"Parsed Concept '{concept_description}': Found terms for {len(language_terms)} languages.")
                    # Example: print(f"  Languages: {list(language_terms.keys())}")
                    found_concepts += 1
                else:
                    print(f"Parsing Warning: Found concept '{concept_description}' but no valid language/term lines matched.")
            else:
                 print(f"Parsing Warning: Found concept '{concept_description}' but no language lines matched the pattern.")

        if found_concepts == 0:
             print("Parsing Warning: No concepts with terms found in the cross-lingual section.")

    except Exception as e:
        print(f"Error parsing keyword report markdown for concepts: {e}")
        print(traceback.format_exc())
        return {} # Return empty on error

    return concepts


# --- New Concurrent Scraping Function ---

def scrape_individual_terms_concurrently(concepts_data: dict):
    """Scrapes patents concurrently for each individual term (max 5 workers), getting up to 50 results per term."""
    print(f"\n--- Starting Concurrent Scraping: Individual terms (max 5 workers, max 50 results/term) ---")
    all_patents = []
    seen_patent_ids = set()
    total_api_calls = 0
    RESULTS_PER_CALL = '50'
    MAX_WORKERS = 5

    if not SCRAPINGDOG_API_KEY:
        print("Scraping skipped: SCRAPINGDOG_API_KEY not configured.")
        return [], 0

    # --- Extract all individual terms --- 
    all_individual_terms = []
    if concepts_data:
        for lang_dict in concepts_data.values():
            for terms_list in lang_dict.values():
                all_individual_terms.extend(terms_list)
        # Remove duplicates 
        all_individual_terms = sorted(list(set(all_individual_terms)))
    
    if not all_individual_terms:
        print("No individual terms found to scrape.")
        return [], 0
        
    print(f"Found {len(all_individual_terms)} unique individual terms to scrape concurrently.")

    # --- Define worker function --- 
    def scrape_single_term(term):
        # print(f"  Queueing scrape for term: '{term}'") # Can be verbose
        result = call_scrapingdog_api(term, 0, num=RESULTS_PER_CALL)
        return term, result # Return term for context in results processing

    # --- Execute concurrently --- 
    futures_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Map future to term for easier error reporting
        futures_map = {executor.submit(scrape_single_term, term): term for term in all_individual_terms}
        print(f"Submitted {len(futures_map)} scraping tasks to {MAX_WORKERS} workers.")
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(futures_map):
            total_api_calls += 1
            term = futures_map[future] # Get term associated with this future
            try:
                term_from_result, result_data = future.result() # Get result from the future
                
                # --- Process results --- 
                if isinstance(result_data, dict) and result_data.get("error"):
                    print(f"    Term '{term}': API Error - {result_data.get('error')}") # Use .get for safety
                    continue 

                if isinstance(result_data, dict) and result_data.get("organic_results") and isinstance(result_data["organic_results"], list):
                    page_results_count = len(result_data['organic_results'])
                    new_patents_on_page = 0
                    for patent in result_data["organic_results"]:
                        if isinstance(patent, dict):
                            patent_id = patent.get("patent_id")
                            if patent_id and patent_id not in seen_patent_ids:
                                url_id_part = patent_id.replace("patent/", "")
                                url = f"https://patents.google.com/patent/{url_id_part}"
                                patent['url'] = url
                                all_patents.append(patent)
                                seen_patent_ids.add(patent_id)
                                new_patents_on_page += 1
                    if new_patents_on_page > 0:
                         print(f"      Added {new_patents_on_page} new unique patents from term '{term}'.")
                    # Optional: Print if 0 results found for a term
                    # elif page_results_count == 0:
                    #     print(f"    Term '{term}': Found 0 results.")
                else:
                    # This case might happen for successful calls with zero results or unexpected format
                    if not (isinstance(result_data, dict) and result_data.get("error")):
                        print(f"    Term '{term}': No organic results found or unexpected format.")
                # --- End result processing ---
                
            except Exception as exc:
                print(f"    Scraping task for term '{term}' generated an exception: {exc}")
                # print(traceback.format_exc()) # Optionally print full traceback

    print(f"--- Concurrent Scraping Finished --- ")
    print(f"Total ScrapingDog API calls attempted: {total_api_calls} (for {len(all_individual_terms)} terms)")
    print(f"Total unique patents collected: {len(all_patents)}")
    return all_patents, total_api_calls

# --- Helper Function for Patent ID Normalization ---

def normalize_patent_id(raw_id: str):
    """Extracts the core publication number from various patent ID formats."""
    if not raw_id or not isinstance(raw_id, str):
        return None
    # Clean potential leading/trailing junk first
    cleaned = raw_id.strip().strip('[]')
    # Handle formats like patent/US.../en or patent/CN...
    if '/' in cleaned:
        parts = cleaned.split('/')
        if len(parts) > 1 and parts[0] == 'patent':
             # Take the part after 'patent/' as the core ID
             return parts[1] 
    # If no slash or not the expected format, assume the cleaned string is the ID
    return cleaned

# --- Main Report Generation Function (Modified) ---

def generate_keyword_report(job_id: str, description_text: str, focus_area: str = None):
    """Generates a report with keywords, initial analysis, and deep-dive analysis, considering a focus area."""
    print(f"Generating full report for Job ID: {job_id}...")
    if focus_area:
        print(f"  Using Focus Area: '{focus_area}'")
    if not description_text:
        return "# Error\n\nInvention description text is empty."

    # --- Stage 1: Keyword Generation --- 
    print("\n--- Stage 1: Generating Keywords ---")
    languages_str = ", ".join(LANGUAGES)
    
    # Add focus area instruction if provided
    focus_instruction_kw = ""
    if focus_area:
        focus_instruction_kw = f"\n**User Focus Area:** The user is particularly interested in aspects related to: '{focus_area}'. Please ensure the generated keywords and concepts strongly reflect this focus."
        
    # --- Restore Full Prompt --- 
    keyword_prompt = f"""
    Act as a world-class patent and non-patent literature search expert with deep experience in multilingual keyword and classification analysis. You possess a profound understanding of patent searching methodologies, including both keyword-based strategies and classification-based approaches. Your expertise extends to recognizing subtle variations in terminology across languages and technical domains.

    Analyze the following invention description provided at the end.{focus_instruction_kw}

    **Background & Challenge:** Patent documents and non-patent literature (NPL) exhibit significant terminological diversity.  A single technical concept can be described using a wide array of terms, synonyms, and phrasings.  Effective prior art searching, especially at a premium level, demands the ability to anticipate and generate this terminological breadth across multiple languages and information sources, including both patent and non-patent literature.  Relying on literal translations or simplistic keyword lists is insufficient for comprehensive discovery.

    **Complex Task - Execute with Expert Precision:**

    1.  **Deep Conceptual Decomposition:**  Thoroughly analyze the invention description to decompose it into its fundamental technical and functional concepts. Identify the core inventive ideas, the problems being solved, and the key advantages claimed. Prioritize concepts directly relevant to the user's focus area, but also consider broader related concepts that might be indirectly relevant. Think in terms of the underlying *technology* and *functionality*, not just the words used to describe it.

    2.  **Multilingual Terminology Generation (Native and Nuanced):** For EACH core concept identified (especially those within the focus area), generate a comprehensive set of **native search terms and short phrases** in EACH of the following languages: {languages_str}.
        *   **Term Variation Mastery:** Critically and expansively consider the full spectrum of synonyms, related terms, technical jargon, industry slang, alternative phrasings, and even misspellings or common abbreviations that might be used to describe the concept in patent documents and NPL *within each target language*. Generate terms that reflect the *terminological landscape* of the field.  Think beyond direct translations and capture the organic language used by experts and inventors in each linguistic context. Consider how the same concept might be described in patent claims, specifications, abstracts, titles, and different types of NPL (academic papers, technical manuals, product brochures, online forums, etc.).
        *   **Classification Awareness (Implicit Term Generation):**  While generating terms, implicitly consider relevant patent classifications (IPC, CPC, USPC) associated with each concept.  Think about terms that are commonly used *within* those classifications, even if not explicitly stated in the invention description. This will help generate terms that are aligned with patent indexing practices.
        *   **Native Linguistic Precision:** Prioritize the most effective *native* terms/phrases for each concept in each language. Avoid literal or overly simplistic translations. Focus on terms that would naturally be used by a native speaker in a technical context. **IMPORTANT: For languages not using the Latin alphabet (e.g., Mandarin, Japanese, Korean), provide terms *only* in their native script. Do NOT include Romanized transliterations.**

    3.  **Cross-Lingual Concept Grouping (Rigorous Accuracy):**  Compare the generated native terms across all languages. Group together terms from different languages ONLY if they represent the **identical core technical concept with a high degree of precision**.  Err on the side of caution and *avoid* grouping terms that are only loosely related or have nuanced differences in meaning. Assign a concise and highly descriptive label to each multi-language concept group, capturing the essence of the shared concept.

    4.  **Language-Specific Nuance Isolation (Targeted Specificity):** Identify native terms that represent concepts, nuances, or technical specificities that are unique to certain languages or lack precise equivalents in others. These terms should **not** be grouped cross-lingually.  These often represent culturally or linguistically specific aspects of the technology.

    5.  **Structured Expert Report Output:** Structure the report using the STRICT format below. Clearly differentiate between cross-lingual concept groups and language-specific terms. *Within each concept group, meticulously list ALL generated terms for each language.*  The report should resemble the output of a highly skilled human search expert, providing a clear and actionable keyword strategy.

    **Output Format (Strict, Multi-Section Markdown - Expert Report Style):**
    Use the following structure precisely. Ensure clean, standard Markdown.  This is formatted like a professional prior art search report.

    ## Preliminary Keyword and Concept Strategy Report (Focus: {focus_area if focus_area else 'General'})
    *For Patent and Non-Patent Literature Searching - Iterative Refinement Recommended*

    ### I. Core Technical Concepts Identified
    This section outlines the key technical and functional concepts extracted from the invention description. These concepts form the foundation for the keyword search strategy.

    *   [Briefly describe Concept 1 (related to focus) - focus on technical essence]
    *   [Briefly describe Concept 2 (related to focus) - focus on technical essence]
    *   ... (List all core concepts identified, prioritize those related to focus)

    ### II. Cross-Lingual Search Concept Groups
    This section presents groups of search terms that represent the same core technical concept across multiple languages.  These term sets are designed for broad and effective searching in multilingual patent and non-patent literature databases.

    **Concept Group 1: [Concept 1 Descriptive Label (Precise and Technical)]**
        *   *Description:* [1-2 sentence precise technical description of the concept]
        *   English: `[Term 1a]`, `[Term 1b]`, `[Term 1c]`, ... (List ALL generated English terms, comma-separated within backticks)
        *   Mandarin: `[Term 1a]`, `[Term 1b]`, `[Term 1c]`, ... (List ALL generated Mandarin terms in native script, comma-separated within backticks)
        *   Japanese: `[Term 1a]`, `[Term 1b]`, ... (List ALL generated Japanese terms in native script, comma-separated within backticks)
        *   Korean: `[Term 1a]`, `[Term 1b]`, `[Term 1c]`, ... (List ALL generated Korean terms in native script, comma-separated within backticks)
        *   German: `[Term 1a]`, `[Term 1b]`, ... (List ALL generated German terms, comma-separated within backticks)
        *   French: `[Term 1a]`, `[Term 1b]`, ... (List ALL generated French terms, comma-separated within backticks)
        *   Spanish: `[Term 1a]`, `[Term 1b]`, ... (List ALL generated Spanish terms, comma-separated within backticks)
        *   Italian: `[Term 1a]`, `[Term 1b]`, ... (List ALL generated Italian terms, comma-separated within backticks)
        *   ... (List ALL requested languages for THIS concept group, include ALL terms generated for each language)

    **Concept Group 2: [Concept 2 Descriptive Label (Precise and Technical)]**
        *   *Description:* [1-2 sentence precise technical description of the concept]
        *   English: `[Term 2a]`, `[Term 2b]`, ...
        *   Mandarin: `[Term 2a]`, `[Term 2b]`, ...
        *   ... (Repeat for all languages and terms)

    ... (Repeat for all cross-lingual concept groups)

    ### III. Language-Specific or Nuanced Search Terms
    This section lists search terms that are specific to particular languages or represent nuances not easily captured by cross-lingual concept groups. These terms can be valuable for targeted searching in specific linguistic contexts.

    *   **Korean:** `[Unique Term A]`, `[Unique Term B]`, ... (List unique Korean terms in native script, comma-separated within backticks)
        *   *Nuance/Context:* [Briefly explain the specific nuance or context of these terms]
    *   **Japanese:** `[Unique Term C]`, ... (List unique Japanese terms in native script, comma-separated within backticks)
        *   *Nuance/Context:* [Briefly explain the specific nuance or context of these terms]
    *   ... (Repeat for other languages with unique terms)

    **Important Formatting and Execution Notes:**
    *   **Conceptual Grouping Accuracy:**  Ensure rigorous accuracy in cross-lingual concept grouping. Only group terms representing truly identical concepts.
    *   **Unique Term Justification:**  Clearly justify why terms are listed as language-specific and describe their unique nuance or context.
    *   **Native Term Effectiveness:**  Prioritize the most effective NATIVE terms per concept/language, reflecting deep terminological understanding and considering synonyms, variations, and technical jargon within each language.
    *   **Comprehensive Term Listing:** **List ALL generated terms for each language together, separated by commas, within the backticks.**
    *   **Search Link Generation Removed:**  Search links are not included in this report as the focus is on generating a comprehensive keyword strategy applicable across various patent and NPL databases.  Adapt these terms for specific database syntax and Boolean operators (AND, OR, NEAR, etc.) as needed during actual searching.
    *   Use standard Markdown list and section formatting.
    *   Do NOT include triple backticks around the final output.

    Invention description is attached below.
    """

    keyword_report_md = call_gemini_for_keywords(keyword_prompt, description_text)

    if keyword_report_md.startswith("# Error"):
        print("Keyword generation failed. Cannot proceed.")
        return keyword_report_md
        
    # --- Stage 2: Scraping & Initial Analysis --- 
    print("\n--- Stage 2: Concurrent Scraping & Initial Prior Art Analysis --- ") 
    # Default messages initialization
    prior_art_analysis_md = "\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nAnalysis could not be performed. Check logs for parsing or scraping errors.\n" 
    deep_dive_reports_md = "\n\n---\n\n## Detailed Prior Art Analysis (Based on Full PDFs)\n\nDeep dive analysis skipped due to errors in previous stages or lack of relevant patents found initially.\n" 
    top_patents_for_deep_dive = []
    scraped_patents_dict = {} 
    scraped_patents_list = [] # Initialize scraped_patents_list
    api_calls_made = 0 # Initialize api_calls_made
    
    all_concepts_data = parse_all_concept_data(keyword_report_md)
    concept_descriptions = list(all_concepts_data.keys()) # Keep for context
    
    # Check if concepts were parsed before attempting scraping
    if all_concepts_data:
        # Call the new concurrent scraping function
        scraped_patents_list, api_calls_made = scrape_individual_terms_concurrently(all_concepts_data)
        
        if scraped_patents_list:
             # Populate dictionary
             normalized_keys_count = 0
             for p_data in scraped_patents_list:
                 if isinstance(p_data, dict):
                     raw_patent_id = p_data.get("patent_id")
                     normalized_key = normalize_patent_id(raw_patent_id)
                     if normalized_key:
                         scraped_patents_dict[normalized_key] = p_data
                         normalized_keys_count += 1
                     else:
                          print(f"Warning: Could not normalize patent ID: {raw_patent_id}")
             print(f"Populated scraped_patents_dict with {normalized_keys_count} entries using normalized keys.")
            
             # Perform initial analysis, passing focus_area
             initial_analysis_md = call_gemini_for_prior_art(description_text, concept_descriptions, scraped_patents_list, focus_area=focus_area)
            
             if initial_analysis_md and not initial_analysis_md.startswith("# Error"):
                 prior_art_analysis_md = initial_analysis_md
                 print("Parsing initial analysis report for top patents...")
                 # Safely parse IDs using regex
                 try:
                     parsed_ids_raw = re.findall(r"^\*\*\d+\.\s+((?:patent/)?\S+)\s+-", initial_analysis_md, re.MULTILINE)
                 except Exception as re_err:
                     print(f"Warning: Regex error parsing top patents: {re_err}")
                     parsed_ids_raw = []
                 
                 top_patent_ids_normalized = []
                 if parsed_ids_raw:
                      # print(f"DEBUG: Raw parsed IDs from analysis: {parsed_ids_raw}") 
                      for raw_id in parsed_ids_raw:
                           normalized_id = normalize_patent_id(raw_id) 
                           if normalized_id:
                                top_patent_ids_normalized.append(normalized_id)
                           else:
                                print(f"Warning: Could not normalize parsed ID: {raw_id}")
                      print(f"Found {len(top_patent_ids_normalized)} top patent IDs (normalized) for deep dive.") # Removed list for brevity
                 
                 if top_patent_ids_normalized:
                     # Retrieve data using normalized keys, checking existence
                     top_patents_for_deep_dive = []
                     missing_ids = []
                     for pid in top_patent_ids_normalized:
                          if pid in scraped_patents_dict:
                               top_patents_for_deep_dive.append(scraped_patents_dict[pid])
                          else:
                               missing_ids.append(pid)
                               
                     retrieved_count = len(top_patents_for_deep_dive)
                     expected_count = len(top_patent_ids_normalized)
                     print(f"Retrieved full data for {retrieved_count}/{expected_count} patents.")
                     if missing_ids:
                          print("WARNING: Not all parsed top patents were found in the scraped data dictionary.")
                          print(f"Missing Normalized IDs: {missing_ids}")
                 else:
                     print("Could not parse/normalize top patent IDs from the initial analysis markdown.")
             else: 
                 # Handle failure of initial analysis call - update default message
                 error_info = initial_analysis_md if initial_analysis_md else "(Unknown Error)"
                 prior_art_analysis_md = f"\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nInitial analysis failed. Error: {error_info}"
        else: 
             # Handle case where scraping yielded no results - update default message
             prior_art_analysis_md = f"\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nNo patent results were found after scraping {api_calls_made} terms concurrently.\n"
    else: 
        # Handle case where no terms were parsed - update default message
        print("No cross-lingual concepts/terms found. Skipping scraping and analysis.")
        prior_art_analysis_md = "\n\n---\n\n## Prior Art Relevance Analysis (Initial - Based on Snippets)\n\nCould not parse any search terms from the keyword report. Unable to perform scraping or analysis.\n"
        
    # --- Stage 3: PDF Deep Dive Analysis --- 
    print(f"\n--- Stage 3: PDF Deep Dive Analysis for {len(top_patents_for_deep_dive)} Top Patents --- ")
    deep_dive_results = []
    if top_patents_for_deep_dive:
        for i, patent_data in enumerate(top_patents_for_deep_dive):
             patent_id = patent_data.get('patent_id', f'Unknown_{i+1}')
             pdf_suffix = patent_data.get('pdf')
             print(f"\nProcessing Deep Dive for: {patent_id} (PDF Suffix: {pdf_suffix}) [{i+1}/{len(top_patents_for_deep_dive)}]")
             
             if not pdf_suffix:
                 print("  Skipping deep dive: No PDF suffix found in scraped data.")
                 deep_dive_results.append(f"### Detailed Analysis for {patent_id}\n\nSkipped: No PDF link found in scraped data.\n")
                 continue
                 
             pdf_bytes = fetch_patent_pdf(pdf_suffix)
             if pdf_bytes:
                 # Pass focus_area to deep dive call
                 analysis_md = call_gemini_for_deep_dive(description_text, patent_data, pdf_bytes, focus_area=focus_area)
                 deep_dive_results.append(analysis_md)
             else:
                 print(f"  Skipping deep dive for {patent_id}: Failed to fetch PDF.")
                 deep_dive_results.append(f"### Detailed Analysis for {patent_id}\n\nSkipped: Failed to download or process PDF from Google Storage.\n")
        
        if deep_dive_results:
             # Update default message only if results exist
            deep_dive_reports_md = "\n\n---\n\n## Detailed Prior Art Analysis (Based on Full PDFs of Top Patents)\n\n" + "\n\n---\n\n".join(deep_dive_results)
        # else: keep default message if no results were generated
    else:
        print("Skipping deep dive analysis as no top patents were identified or retrieved from the initial analysis.")
        # Keep default deep_dive_reports_md message

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

def call_gemini_for_deep_dive(description_text, patent_data, pdf_bytes, focus_area=None):
    """Calls Gemini with the description and full patent PDF for detailed analysis, considering a focus area."""
    if not pdf_bytes:
        return f"### Detailed Analysis for {patent_data.get('patent_id', 'Unknown Patent')}\n\nCould not fetch or process the PDF for detailed analysis.\n"

    patent_id = patent_data.get('patent_id', 'N/A')
    patent_title = patent_data.get('title', 'N/A')
    patent_url = patent_data.get('url', '#') 

    # Add focus area instruction if provided
    focus_instruction_dd = ""
    if focus_area:
        focus_instruction_dd = f"\n**User Focus Area:** The user is particularly interested in aspects related to: '{focus_area}'. Please ensure your analysis specifically addresses the relevance of this patent to the user's focus area within the invention description."

    # --- Restore Full Prompt --- 
    prompt = f"""
    Act as an expert patent analyst performing a detailed prior art relevance assessment.{focus_instruction_dd}

    **Input:**
    1.  The Full Invention Description (provided in context).
    2.  The Full Text of a specific Patent Document (attached PDF).
    3.  User Focus Area (if specified above).

    **Task:**
    Based on a thorough review of BOTH the invention description and the attached full patent PDF, provide a detailed analysis of the patent's relevance as prior art to the invention description, paying close attention to the specified user focus area.

    **Output Format (Strict Markdown):**

    ### Detailed Analysis: {patent_id} - {patent_title}

    **Link:** [[Link]]({patent_url})

    **User Focus:** {focus_area if focus_area else 'General'}

    **Summary of Patent:** [Provide a brief 2-4 sentence summary of the key technology disclosed in the attached patent PDF, noting aspects potentially relevant to the user focus.]

    **Detailed Relevance Assessment (Focus: {focus_area if focus_area else 'General'}):**
    *   [Analyze specific sections/claims/figures of the attached patent that are most relevant to the core concepts of the invention description, **especially those related to the user's focus area**.]
    *   [Discuss the degree of overlap or similarity between the patent's disclosure and the invention description, emphasizing the focus area.]
    *   [Identify key similarities and differences in the technical approaches or solutions, particularly regarding the focus area.]
    *   [Comment on whether this patent potentially anticipates or renders obvious key aspects of the invention description, especially within the focus area.]

    **Conclusion:** [Provide a concluding statement on the overall relevance of this specific patent as prior art to the invention description, specifically addressing its relevance to the user's focus area based on the full PDF review.]

    **Important:** Base your analysis **strictly** on the provided invention description and the attached full patent PDF document. Do not invent information not present in the inputs. Give special weight to the user's focus area.
    """

    pdf_file_data = {
        'mime_type': 'application/pdf',
        'data': pdf_bytes
    }

    analysis_result = call_gemini_with_retry(
        prompt,
        context_text=description_text, 
        files=[pdf_file_data],         
        task_description=f"Deep Dive Analysis for {patent_id}"
    )
    return analysis_result 