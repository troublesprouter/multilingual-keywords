import os
import google.generativeai as genai
from google.generativeai import types
from pathlib import Path
import time
import re
import threading # Added for parallel processing
from collections import defaultdict # For grouping subclasses

# Configure the API key
# Load environment variables from .env file if it exists.
env_path = Path('.env')
if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, value = line.split('=', 1)
            if key == 'GOOGLE_API_KEY' and value and value != 'YOUR_API_KEY_HERE':
                os.environ['GOOGLE_API_KEY'] = value
                print("Loaded GOOGLE_API_KEY from .env file.")
                break

API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    print("Error: GOOGLE_API_KEY not found in environment variables or .env file.")
    exit(1)

genai.configure(api_key=API_KEY)

# --- Configuration ---
PATENT_SPEC_FILE = "spec.txt"
SCHEME_PDF_DIRECTORY = "pdfs/schemes" # Updated directory for scheme files
DEFINITION_PDF_DIRECTORY = "pdfs/definitions" # New directory for definition files
# MODEL_NAME = "models/gemini-2.0-flash-thinking-exp-01-21" # Using 2.0 Flash thinking model
MODEL_NAME = "models/gemini-2.0-flash-lite" # Using 2.0 Flash lite model
# MODEL_NAME = "models/gemini-2.5-pro-preview-03-25"
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds

# --- Helper Functions ---

def read_text_file(filepath):
    """Reads content from a text file."""
    try:
        return Path(filepath).read_text()
    except FileNotFoundError:
        print(f"Error: File not found - {filepath}")
        exit(1)
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        exit(1)

def list_pdf_files(directory, pattern):
    """Lists PDF files in a directory matching a pattern."""
    try:
        pdf_path = Path(directory)
        if not pdf_path.is_dir():
            print(f"Error: Directory not found - {directory}")
            return []
        # Ensure pattern finds files within the specified directory
        return sorted([str(f) for f in pdf_path.glob(pattern) if f.is_file()])
    except Exception as e:
        print(f"Error listing PDF files in {directory}: {e}")
        return []

def call_gemini_api(prompt, file_paths, patent_text):
    """Calls the Gemini API with text prompt, PDF files (passed as dicts), and patent text."""
    print(f"\n--- Calling Gemini API ---")
    print(f"Prompt snippet: {prompt[:100]}...")
    print(f"Number of PDF files to process: {len(file_paths)}")

    model = genai.GenerativeModel(MODEL_NAME)

    # Prepare content parts: prompt, patent text, and PDF file data as dictionaries
    content_parts = [
        prompt,
        "--- PATENT SPECIFICATION START ---",
        patent_text,
        "--- PATENT SPECIFICATION END ---",
        "\n--- CPC SCHEME DOCUMENTS START ---"
    ]

    files_attached_count = 0
    for pdf_path in file_paths:
        try:
            pdf_file = Path(pdf_path)
            if pdf_file.exists() and pdf_file.stat().st_size > 0:
                print(f"Reading bytes for PDF: {pdf_path}")
                pdf_data = pdf_file.read_bytes()
                # Pass file data as a dictionary {mime_type, data}
                content_parts.append({
                    'mime_type': 'application/pdf',
                    'data': pdf_data
                })
                files_attached_count += 1
            else:
                print(f"Warning: Skipping empty or non-existent file: {pdf_path}")
        except Exception as e:
            print(f"Warning: Could not read or prepare file {pdf_path}: {e}")

    content_parts.append("--- CPC SCHEME DOCUMENTS END ---")
    print(f"Total files attached as parts: {files_attached_count}")

    if files_attached_count == 0:
        print("Error: No PDF files were successfully prepared. Cannot proceed with API call.")
        return None

    # Retry mechanism
    for attempt in range(MAX_RETRIES):
        response = None # Initialize response to None for each attempt
        try:
            print(f"Sending request (Attempt {attempt + 1}/{MAX_RETRIES})...")
            start_time = time.time()
            response = model.generate_content(
                contents=content_parts,
                generation_config=types.GenerationConfig(
                    temperature=0.2,
                ),
                request_options={'timeout': 600}
            )
            elapsed_time = time.time() - start_time
            print(f"Request completed in {elapsed_time:.2f} seconds.")

            # Process response - Safely extract text
            response_text = ""
            if response.candidates and response.candidates[0].content.parts:
                response_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            elif response.parts: # Fallback check if candidates structure isn't as expected
                response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))

            if response_text:
                # print(f"Raw Gemini Response Text: {response_text[:500]}...") # Debugging
                return response_text.strip()
            else:
                # Check for blocking/finish reasons even if no text parts
                if response and response.prompt_feedback:
                    print(f"Warning: Prompt may have been blocked. Feedback: {response.prompt_feedback}")
                elif response and response.candidates:
                    print(f"Warning: Generation may have stopped. Finish Reason: {response.candidates[0].finish_reason}, Safety: {response.candidates[0].safety_ratings}")
                else:
                    print("Warning: Received empty or unexpected response structure from API.")
                # Continue to retry loop if possible, or return empty if retries exhausted
                if attempt == MAX_RETRIES - 1:
                    return "" # Return empty after last attempt if response was empty/problematic
                else:
                    print(f"Retrying due to empty/problematic response...")
                    time.sleep(RETRY_DELAY)
                    continue # Go to next attempt
        except types.generation_types.BlockedPromptException as bpe:
            print(f"Error: Prompt was blocked. {bpe}")
            if response and response.prompt_feedback: # Log details if response object exists
                print(f"Prompt Feedback: {response.prompt_feedback}")
            return None # Indicate fatal error
        except types.generation_types.StopCandidateException as sce:
            print(f"Error: Generation stopped unexpectedly. {sce}")
            if response and response.candidates: # Log details if response object exists
                print(f"Finish Reason: {response.candidates[0].finish_reason}")
                print(f"Safety Ratings: {response.candidates[0].safety_ratings}")
            return None # Indicate fatal error
        except Exception as e:
            print(f"Error during Gemini API call (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print("Max retries reached. Skipping this API call.")
                return None # Indicate failure after retries

    return None # Indicate failure (if loop completes without success)

def parse_response_for_codes(response_text, level):
    """Parses Gemini response to extract CPC codes based on the level."""
    if not response_text:
        return []

    codes = set()
    try:
        if level == 1:
            # Level 1: Expecting subclasses (e.g., B60L) or second-level (e.g., B60)
            # Pattern 1: Match subclasses explicitly (e.g., B60L, F02M)
            pattern1 = r'\b([A-HY]\d{2}[A-Z])\b'
            found1 = re.findall(pattern1, response_text)
            codes.update(f.upper() for f in found1)

            # Pattern 2: Match second-level codes (e.g., B60, F02) just in case
            # If subclasses were found, these probably won't be used unless they are the only match
            if not codes: # Only look for second-level if no subclasses found
                 pattern2 = r'\b([A-HY]\d{2,3})\b'
                 found2 = re.findall(pattern2, response_text)
                 codes.update(f.upper() for f in found2)

        elif level == 2: # Renamed Level 3 to Level 2 (Final Step)
            # Level 2 (Final): Expecting fine-grained codes.
            # Pattern 1: Codes with a slash (e.g., A61K 31/00, H01L 21/02)
            pattern1 = r'\b([A-HY]\d{2}[A-Z]\s*\d{1,4}/\d{2,6})\b'
            codes.update(m.strip() for m in re.findall(pattern1, response_text))

            # Pattern 2: Codes with slash and further subgroup (e.g., H01L 29/786/12, G06F 17/30867)
            pattern2 = r'\b([A-HY]\d{2}[A-Z]\s*\d{1,4}/\d{2,}[A-Z0-9/]*)\b'
            codes.update(m.strip() for m in re.findall(pattern2, response_text))

            # Pattern 3: Codes without a slash but potentially deep (e.g., H01L 29/786, B23P 19/04)
            pattern3 = r'\b([A-HY]\d{2}[A-Z]\s*\d{1,}\.?\d*)\b'
            codes.update(m.strip() for m in re.findall(pattern3, response_text))

            # Ensure subclasses themselves are not included if more specific codes exist
            subclass_pattern = r'^[A-HY]\d{2}[A-Z]$'
            specific_codes_found = any('/' in code or re.search(r'\d$', code) for code in codes)
            if specific_codes_found:
                 codes = {code for code in codes if not re.match(subclass_pattern, code)}
        else:
            print(f"Warning: Unknown level '{level}' for parsing codes.")
            return []

    except Exception as e:
        print(f"Error during regex parsing (Level {level}): {e}")
        return []

    # Post-processing: Clean up and ensure uniqueness
    cleaned_codes = set()
    for code in codes:
        cleaned_code = ' '.join(code.strip().split())
        if re.match(r'^[A-HY]', cleaned_code):
             cleaned_codes.add(cleaned_code)

    print(f"Level {level} - Parsed codes: {sorted(list(cleaned_codes))}")
    return sorted(list(cleaned_codes))

# --- Report Generation Function ---
def generate_report(final_codes, all_pdfs_used_in_level2, patent_spec):
    """Generates a detailed report explaining the final CPC codes using Gemini, including search links."""
    print("\n--- Generating Final Consolidated Report ---")
    if not final_codes:
        return "No final CPC codes were identified."

    # Use a set for unique PDFs
    unique_pdfs = sorted(list(set(all_pdfs_used_in_level2)))
    print(f"Generating report using {len(unique_pdfs)} unique context PDFs.")

    # Prepare a version of codes without spaces for URL generation instructions
    codes_for_urls = {code: re.sub(r'\s+', '', code) for code in final_codes}

    report_prompt = f"""
    Act as a world-class patent expert analyzing the provided invention description and relevant Cooperative Patent Classification (CPC) documents (schemes and definitions).

    The following CPC codes have been identified as potentially relevant after analyzing specific classification areas in parallel:
    {', '.join(final_codes)}

    Based *only* on the provided invention description and the context from the attached relevant CPC scheme and definition documents, please generate a detailed consolidated report. **Format the entire response using excellent, clean Markdown suitable for direct rendering as professional-looking HTML.**

    **Report Structure:**
    1.  **Overall Summary:** Start with a brief overall summary identifying the *most pertinent* classification areas and specific codes for a prior art search. **For the specific codes mentioned as most pertinent in this summary, include clickable search links** using the format specified below (Espacenet and Google Patents, code with spaces removed).
    2.  **Detailed Code Analysis:** Following the summary, provide a detailed breakdown for each identified code listed in the consolidated list provided above.

    **Format for Detailed Code Analysis Section:**
    For each identified code:
    *   Use a Markdown heading (like `##` or `###`) for the full CPC code.
    *   **Immediately after the heading, provide search links:** Create two Markdown links using the code **with spaces removed** for the query part:
        *   Espacenet: `[Espacenet](https://worldwide.espacenet.com/patent/search?q=cpc%20%3D%20%22CODE_NO_SPACE%22)`
        *   Google Patents: `[Google Patents](https://patents.google.com/?q=(CODE_NO_SPACE)&oq=CODE_NO_SPACE)`
        *   Replace `CODE_NO_SPACE` with the specific code without spaces (e.g., for `B60L 1/00`, use `B60L1/00` in the URLs).
    *   **Subject Matter:** Briefly explain the technical subject matter covered by this code, referencing the provided scheme/definition documents.
    *   **Relevance:** Explain *why* this specific code is likely relevant to the invention description, citing specific aspects from the description.
    *   **Expert Comments:** Add any pertinent expert comments regarding the classification, potential search strategies using this code, or nuances related to this classification area.

    Ensure the report flows logically, starting with the summary and then moving to the detailed analysis. **Use Markdown elements like headings, bold text, bullet points, etc., effectively for clarity and visual appeal.** Do NOT wrap the final response in triple backticks.

    Invention description and relevant CPC documents are attached.
    """

    # Use the combined list of unique PDFs from all Level 2 parallel calls
    report_text = call_gemini_api(report_prompt, unique_pdfs, patent_spec)

    if not report_text:
        return "Failed to generate the final consolidated report."

    print("Consolidated report generation complete.")
    return report_text

# --- Helper for Parallel Level 2 Processing ---
def _process_subclass_group(group_key, subclasses_in_group, patent_spec, results_dict):
    """Processes a single group of subclasses in a thread."""
    print(f"-- Starting thread for group: {group_key} (Subclasses: {subclasses_in_group}) --")
    pdfs_for_group = []
    pdfs_found_for_report = []

    for subclass in subclasses_in_group:
        # Find Scheme PDF
        scheme_pdf_name = f"cpc-scheme-{subclass}.pdf"
        scheme_pdf_path = Path(SCHEME_PDF_DIRECTORY) / scheme_pdf_name
        if scheme_pdf_path.is_file():
            pdfs_for_group.append(str(scheme_pdf_path))
            pdfs_found_for_report.append(str(scheme_pdf_path))
        # else: print(f"Group {group_key}: Scheme PDF not found: {scheme_pdf_path}") # Reduce noise

        # Find Definition PDF
        definition_pdf_name = f"cpc-definition-{subclass}.pdf"
        definition_pdf_path = Path(DEFINITION_PDF_DIRECTORY) / definition_pdf_name
        if definition_pdf_path.is_file():
            pdfs_for_group.append(str(definition_pdf_path))
            pdfs_found_for_report.append(str(definition_pdf_path))
        # else: print(f"Group {group_key}: Definition PDF not found: {definition_pdf_path}") # Reduce noise

    if not pdfs_for_group:
        print(f"-- Thread {group_key}: No PDFs found for subclasses {subclasses_in_group}. Skipping API call. --")
        results_dict[group_key] = ([], []) # Store empty results and no PDFs used
        return

    print(f"-- Thread {group_key}: Found {len(pdfs_for_group)} PDFs. Calling API... --")
    group_prompt = f"""
    Based on an initial analysis suggesting relevance in subclasses starting with letters in the group '{group_key}' (specifically {subclasses_in_group}), perform a detailed analysis of the invention description against ONLY the provided specific CPC subclass scheme AND definition documents for THIS group.
    Identify the **most relevant fine-grained CPC codes** (e.g., B60L 1/00, F02M 37/00) within these specific subclasses that precisely describe the invention's technical features.
    Extract the specific codes including the group and potentially subgroup numbers (e.g., H01L 29/786).
    List ONLY the final, most specific CPC codes relevant to the core inventive concept FOUND WITHIN THIS {group_key} GROUP. Provide the list clearly, separated by commas or newlines.
    Example for group AB: A61K 31/00, B60L 15/20
    """

    group_response = call_gemini_api(group_prompt, pdfs_for_group, patent_spec)
    group_final_codes = parse_response_for_codes(group_response, 2) # Use level 2 parsing for fine-grained

    print(f"-- Thread {group_key}: Finished. Found codes: {group_final_codes} --")
    # Store results and the PDFs actually used for this group
    results_dict[group_key] = (group_final_codes, pdfs_found_for_report)


# --- Main Classification Function ---
def run_classification_process(patent_spec):
    """Runs the full 2-level CPC classification (parallel Level 2) and report generation process."""
    if not patent_spec:
        return "Error: Invention description text is empty."

    # === Level 1: Identify Relevant Subclasses ===
    print("\n=== Level 1: Identifying Relevant Subclasses ===")
    level1_pdfs = list_pdf_files(SCHEME_PDF_DIRECTORY, "cpc-scheme-[A-HY].pdf")
    if not level1_pdfs:
        error_msg = f"Error: No top-level scheme PDFs (cpc-scheme-A.pdf, etc.) found in {SCHEME_PDF_DIRECTORY}"
        print(error_msg)
        return error_msg

    # Modified prompt for Level 1 - Encouraging broader results
    level1_prompt = f"""
    Analyze the following invention description (which could be an abstract, summary, or detailed text) in the context of the provided top-level CPC classification scheme documents (A-Y).
    Identify **the relevant CPC subclasses** (e.g., B60L, F02M, H01L) that relate to the core concepts or different aspects of the invention described. 
    Be inclusive where multiple areas seem applicable. The goal is to capture important starting points for a prior art search while maintaining reasonable focus.
    Focus on the core inventive concept described in the text.
    List ONLY the identified subclasses. Provide the list clearly, separated by commas or newlines. Example: B60L, F02M, H01L, B60K, F02D
    """
    level1_response = call_gemini_api(level1_prompt, level1_pdfs, patent_spec)

    print("--- DEBUG: Raw Level 1 Response ---")
    print(level1_response or "<API call failed or returned empty response>")
    print("--- END DEBUG: Raw Level 1 Response ---")

    # Level 1 now parses subclasses directly
    level1_subclasses = parse_response_for_codes(level1_response, 1)

    if not level1_subclasses:
        error_msg = "Level 1 analysis failed or yielded no subclasses. Stopping."
        print(error_msg)
        return error_msg

    # === Level 2 (Final): Identify Fine-Grained Codes (Parallel Processing) ===
    print("\n=== Level 2 (Final): Identifying Fine-Grained Codes (Parallel by Letter Pair) ===")

    # Group subclasses by letter pairs (AB, CD, EF, GH, Y)
    letter_groups = {
        'AB': ['A', 'B'],
        'CD': ['C', 'D'],
        'EF': ['E', 'F'],
        'GH': ['G', 'H'],
        'Y': ['Y']
    }
    grouped_subclasses = defaultdict(list)
    for subclass in level1_subclasses:
        if subclass and len(subclass) >= 1:
            start_letter = subclass[0].upper()
            found_group = False
            for group_key, letters_in_group in letter_groups.items():
                if start_letter in letters_in_group:
                    grouped_subclasses[group_key].append(subclass)
                    found_group = True
                    break
            if not found_group:
                 print(f"Warning: Subclass '{subclass}' did not fit into defined letter groups.") # Should not happen for A-H, Y

    # Filter out empty groups
    active_groups = {k: v for k, v in grouped_subclasses.items() if v}
    print(f"Grouped subclasses for parallel processing (by pair): {dict(active_groups)}")

    threads = []
    thread_results = {} # Dictionary to store results from threads
    all_pdfs_used_in_level2 = [] # Collect all PDFs used across threads

    # Launch threads for each active group
    for group_key, subclasses_in_group in active_groups.items():
        thread = threading.Thread(
            target=_process_subclass_group, 
            args=(group_key, subclasses_in_group, patent_spec, thread_results)
        )
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    print("Waiting for parallel Level 2 threads to complete...")
    for thread in threads:
        thread.join()
    print("All Level 2 threads finished.")

    # Consolidate results
    consolidated_final_codes = set()
    for group_key, (group_codes, group_pdfs_used) in thread_results.items():
        print(f"Results from Group {group_key}: {group_codes}")
        consolidated_final_codes.update(group_codes)
        all_pdfs_used_in_level2.extend(group_pdfs_used)
        
    final_codes_list = sorted(list(consolidated_final_codes))

    if not final_codes_list:
        error_msg = "Level 2 (Parallel Final) analysis failed or yielded no final codes across all groups."
        print(error_msg)
        return "Level 2 (Final) analysis completed, but no specific CPC codes could be reliably extracted."

    print("\n=== Final Consolidated Relevant CPC Codes Found ===")
    for code in final_codes_list:
        print(code)
    print("============================================")

    # === Generate Final Report ===
    # Use the consolidated codes and the combined list of PDFs used in L2
    final_report = generate_report(final_codes_list, all_pdfs_used_in_level2, patent_spec)
    print("\n=== Expert Classification Report Preview (first 500 chars) ===")
    print(final_report[:500] + "...")
    print("=========================================================")
    return final_report # Return the full report string

# --- Original Main Execution Logic (for direct script run) ---
def main():
    print("Starting Patent CPC Classification Process (Direct Run)...")
    print(f"Reading patent specification from: {PATENT_SPEC_FILE}")
    patent_spec_text = read_text_file(PATENT_SPEC_FILE)
    if not patent_spec_text:
        return
    
    # Call the main classification function
    report = run_classification_process(patent_spec_text)
    
    # Print the final report (already partially printed inside the function)
    print("\n--- Full Report (Direct Run) ---")
    print(report)
    print("--------------------------------")

if __name__ == "__main__":
    main() 