import os
import google.generativeai as genai
from google.generativeai import types
import time
import re
import urllib.parse

# Configure the API key (Loads from .env via app.py)
API_KEY = os.environ.get("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not found for keyword_generator module.")

# --- Configuration ---
MODEL_NAME = "models/gemini-2.0-flash-thinking-exp-01-21" # Using 2.0 Flash thinking model
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds
LANGUAGES = ["English", "Mandarin", "Japanese", "Korean", "German", "French", "Spanish", "Italian"]

# --- Main Keyword Generation Function ---

def call_gemini_for_keywords(prompt, description_text):
    """Calls the Gemini API with text prompt and description text."""
    if not API_KEY:
         return "# Error\n\nGOOGLE_API_KEY not configured."
         
    print(f"\n--- Calling Gemini API for Keywords ---")
    print(f"Prompt snippet: {prompt[:100]}...")

    model = genai.GenerativeModel(MODEL_NAME)
    content_parts = [prompt, "--- INVENTION DESCRIPTION START ---", description_text, "--- INVENTION DESCRIPTION END ---"]

    # Retry mechanism
    for attempt in range(MAX_RETRIES):
        response = None
        try:
            print(f"Sending keyword request (Attempt {attempt + 1}/{MAX_RETRIES})...")
            start_time = time.time()
            response = model.generate_content(
                contents=content_parts,
                generation_config=types.GenerationConfig(temperature=0.5), # Slightly higher temp for keyword creativity
                request_options={'timeout': 300} # 5 minute timeout
            )
            elapsed_time = time.time() - start_time
            print(f"Keyword request completed in {elapsed_time:.2f} seconds.")

            response_text = ""
            if response.candidates and response.candidates[0].content.parts:
                response_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            elif response.parts:
                response_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))

            if response_text:
                return response_text.strip()
            else:
                 if response and response.prompt_feedback:
                     print(f"Warning: Prompt may have been blocked. Feedback: {response.prompt_feedback}")
                 elif response and response.candidates:
                     print(f"Warning: Generation may have stopped. Finish Reason: {response.candidates[0].finish_reason}, Safety: {response.candidates[0].safety_ratings}")
                 else:
                      print("Warning: Received empty or unexpected response structure from API.")
                 if attempt == MAX_RETRIES - 1:
                      return "# Error\n\nReceived empty or problematic response from API after retries."
                 else:
                     print(f"Retrying keyword request due to empty/problematic response...")
                     time.sleep(RETRY_DELAY)
                     continue

        except Exception as e:
            print(f"Error during Gemini API keyword call (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                print("Max retries reached for keyword API call.")
                return f"# Error\n\nAn unexpected error occurred after {MAX_RETRIES} attempts: {e}"

    return "# Error\n\nKeyword generation failed after retries."

def generate_keyword_report(description_text):
    """Generates a report with multilingual keywords and search links for all languages."""
    print("Generating keyword report...")
    if not description_text:
        return "Error: Invention description text is empty."

    languages_str = ", ".join(LANGUAGES)
    # Reverting to nested list prompt, emphasizing newlines and structure
    prompt = f"""
    Act as a world-class patent search expert specializing in multilingual keyword analysis.
    Analyze the following invention description.

    **Task:**
    1.  Identify the core inventive concepts and key technical features.
    2.  Generate a concise list of the **5-7 most effective and distinct English keyword search terms or short phrases** for finding prior art related to this invention.
    3.  For each English keyword/phrase identified, provide translations into the following languages: {languages_str}.
    4.  For **each keyword/phrase in EACH language (including English)**, provide a direct search link for **Google Patents**, using the **URL-encoded version of that specific language's term**.

    **Output Format (Strict Markdown List Format):**
    Use the following structure exactly. Ensure excellent Markdown formatting (headings, bolding, lists, **newlines**, **proper indentation**) for a clean, professional, and highly readable report. Each language and its link MUST be on separate lines, clearly indented.

    ## Keyword Search Strategy Report

    ### Core Concepts
    *   [Briefly list 2-3 core concepts identified]

    ### Recommended Keywords, Translations & Search Links

    **1. [English Keyword/Phrase 1]**
        *   **English:**
            *   Term: `[English Keyword/Phrase 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_ENGLISH_TERM_1)
        *   **Mandarin:**
            *   Term: `[Mandarin Translation 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_MANDARIN_TERM_1)
        *   **Japanese:**
            *   Term: `[Japanese Translation 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_JAPANESE_TERM_1)
        *   **Korean:**
            *   Term: `[Korean Translation 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_KOREAN_TERM_1)
        *   **German:**
            *   Term: `[German Translation 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_GERMAN_TERM_1)
        *   **French:**
            *   Term: `[French Translation 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_FRENCH_TERM_1)
        *   **Spanish:**
            *   Term: `[Spanish Translation 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_SPANISH_TERM_1)
        *   **Italian:**
            *   Term: `[Italian Translation 1]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_ITALIAN_TERM_1)

    **2. [English Keyword/Phrase 2]**
        *   **English:**
            *   Term: `[English Keyword/Phrase 2]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_ENGLISH_TERM_2)
        *   **Mandarin:**
            *   Term: `[Mandarin Translation 2]`
            *   Google Patents: [Search](https://patents.google.com/?q=URL_ENCODED_MANDARIN_TERM_2)
        *   ... (Repeat for all languages and all English keywords, maintaining the clear nested list format with newlines and indentation)

    ... (Continue for all English keywords)

    **Important Formatting Notes:**
    *   Replace `URL_ENCODED_LANG_TERM_X` with the **URL-encoded version** of the keyword/phrase **in that specific language**.
    *   Provide accurate translations.
    *   Use backticks (`) around the keyword/translation.
    *   Ensure the final output is clean, well-structured Markdown using **appropriate nested lists, indentation, and placing each language on its own clearly marked line**.
    *   Do NOT include triple backticks around the final output.

    Invention description is attached below.
    """

    raw_report = call_gemini_for_keywords(prompt, description_text)
    return raw_report 