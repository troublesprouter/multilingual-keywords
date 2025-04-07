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
    Analyze the following invention description provided at the end.

    **Complex Task - Follow Carefully:**

    1.  **Identify Core Concepts:** Thoroughly analyze the invention description to identify the distinct core technical concepts or inventive ideas. These core concepts may appear in any language in the description and may not always have direct English equivalents or translations.
    2.  **Generate Native Terms (All Languages):** For EACH core concept identified, generate the most effective and natural search term or short phrase in EACH of the following languages: {languages_str}. Focus on finding the best native term for the concept in that language, not just a literal translation from English.
    3.  **Analyze and Group:** Compare all the native terms generated across all languages. Group together terms from different languages ONLY IF they represent the **exact same core concept**. Assign a clear description to each multi-language concept group.
    4.  **Isolate Unique Terms:** Identify native terms that represent concepts or nuances specific to one or only a few languages, or terms that do not have precise conceptual equivalents in the other languages. These should NOT be included in the multi-language groups.
    5.  **Format Output:** Structure the report using the STRICT format below. Clearly separate the grouped cross-lingual concepts from the unique/language-specific terms.

    **Output Format (Strict, Multi-Section Markdown):**
    Use the following structure precisely. Ensure clean, standard Markdown (lists, indentation, newlines) for readability.

    ## Keyword Search Strategy Report

    ### Core Concepts Identified
    *   [Briefly describe Concept 1]
    *   [Briefly describe Concept 2]
    *   ... (List all distinct concepts found)

    ### Cross-Lingual Search Concepts
    (List concepts found to have precise equivalents across multiple languages)

    **Concept 1: [Concept 1 Description from above]**
        *   English: `[Native English Term for Concept 1]` - [Search](https://patents.google.com/?q=URL_ENCODED_ENGLISH_TERM_1)
        *   Mandarin: `[Native Mandarin Term for Concept 1]` - [Search](https://patents.google.com/?q=URL_ENCODED_MANDARIN_TERM_1)
        *   ... (List ALL languages where a term for THIS EXACT concept was generated)

    **Concept 2: [Concept 2 Description from above]**
        *   German: `[Native German Term for Concept 2]` - [Search](https://patents.google.com/?q=URL_ENCODED_GERMAN_TERM_2)
        *   French: `[Native French Term for Concept 2]` - [Search](https://patents.google.com/?q=URL_ENCODED_FRENCH_TERM_2)
        *   ... (List ALL languages where a term for THIS EXACT concept was generated)

    ... (Repeat for other grouped concepts)

    ### Language-Specific or Nuanced Search Terms
    (List terms that are unique, nuanced, or did not have precise equivalents for grouping)

    *   Korean: `[Native Korean Term representing a unique concept/nuance]` - [Search](https://patents.google.com/?q=URL_ENCODED_UNIQUE_KOREAN_TERM)
    *   Spanish: `[Native Spanish Term representing a unique concept/nuance]` - [Search](https://patents.google.com/?q=URL_ENCODED_UNIQUE_SPANISH_TERM)
    *   ... (List all such unique/nuanced terms with their language)

    **Important Formatting Notes:**
    *   Accurately perform the conceptual grouping. Only include terms in a group if they match the EXACT concept.
    *   List ungrouped/unique terms clearly in the second section.
    *   Provide the most effective NATIVE term for each concept in each listed language.
    *   Replace `URL_ENCODED...` with the actual URL-encoded term for the Google Patents search link.
    *   Use backticks (`) around all search terms/phrases.
    *   Use standard Markdown list formatting with appropriate indentation (spaces) and newlines.
    *   Do NOT include triple backticks around the final output.

    Invention description is attached below.
    """

    raw_report = call_gemini_for_keywords(prompt, description_text)
    return raw_report 