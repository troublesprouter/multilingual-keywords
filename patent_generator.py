import os
import google.generativeai as genai
from google.generativeai import types
import time
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure the API key
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: GOOGLE_API_KEY not found in patent_generator.py.")

# --- Configuration ---
# Select appropriate model - consider a more powerful one for drafting if needed
MODEL_NAME = "models/gemini-2.5-pro-preview-03-25" 
MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds
LLM_TIMEOUT = 600 # Allow longer timeout for spec generation

# --- Reusable Gemini API Call Function (Adapted from keyword_generator) ---

def call_gemini_with_retry(prompt, context_text=None, files=None, task_description="API call"):
    """Generic function to call Gemini API with retry logic."""
    if not GEMINI_API_KEY:
         return f"# Error\n\nGOOGLE_API_KEY not configured for {task_description}."

    print(f"\n--- Calling Gemini API for {task_description} --- ")
    # Reduced print verbosity slightly for this app
    # print(f"Prompt context length hint: {len(prompt) + (len(context_text) if context_text else 0)}")

    model = genai.GenerativeModel(MODEL_NAME)
    content_parts = [prompt]
    if context_text:
        if not isinstance(context_text, str):
             print(f"Warning: context_text is not a string, type: {type(context_text)}. Converting...")
             context_text = str(context_text)
        content_parts.extend(["--- USER PROVIDED CONTEXT START ---", context_text, "--- USER PROVIDED CONTEXT END ---"])
    
    # Note: File input not currently used for spec generation, but function supports it
    if files: 
         print("Warning: Files provided to call_gemini_with_retry but not expected for spec generation.")

    for attempt in range(MAX_RETRIES):
        response = None
        try:
            print(f"Sending {task_description} request (Attempt {attempt + 1}/{MAX_RETRIES})...")
            start_time = time.time()
            response = model.generate_content(
                contents=content_parts,
                generation_config=types.GenerationConfig(temperature=0.5), # Slightly higher temp might be ok for drafting
                request_options={'timeout': LLM_TIMEOUT} 
            )
            elapsed_time = time.time() - start_time
            print(f"{task_description} request completed in {elapsed_time:.2f} seconds.")

            # Simplified text extraction
            response_text = response.text if hasattr(response, 'text') else None
            if not response_text and response.candidates:
                 try:
                      response_text = response.candidates[0].content.parts[0].text
                 except (AttributeError, IndexError):
                      pass # Stick with None if complex structure fails

            if response_text:
                # Basic check for refusal, might need refinement
                if "cannot fulfill" in response_text.lower() or "unable to create" in response_text.lower():
                     print(f"Warning: Potential refusal detected in response for {task_description}.")
                     # Return refusal directly, maybe wrap in error markdown
                     return f"# Generation Issue\n\nModel indicated difficulty: {response_text}"

                return response_text.strip()
            else:
                 # Log blocking/finish reasons if available
                 if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                     print(f"Warning: Prompt may have been blocked. Feedback: {response.prompt_feedback}")
                 elif response and hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                     print(f"Warning: Generation may have stopped. Finish Reason: {response.candidates[0].finish_reason}, Safety: {response.candidates[0].safety_ratings}")
                 else:
                      print(f"Warning: Received empty or unexpected response structure from API: {response}")

                 if attempt == MAX_RETRIES - 1:
                      return f"# Error\n\nReceived empty or problematic response from API for {task_description} after {MAX_RETRIES} attempts."
                 else:
                     print(f"Retrying {task_description} request due to empty/problematic response...")
                     time.sleep(RETRY_DELAY * (attempt + 1))

        except Exception as e:
            print(f"Error during Gemini API {task_description} call (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            print(traceback.format_exc())
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY * (attempt + 1)} seconds...")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                print(f"Max retries reached for {task_description} API call.")
                # Return error in markdown format for UI
                return f"# Error\n\nAn unexpected error occurred during {task_description} after {MAX_RETRIES} attempts: {e}\n\n```\n{traceback.format_exc()}\n```"

    return f"# Error\n\n{task_description} failed after {MAX_RETRIES} retries."


# --- Specification Generation Logic ---

SPECIFICATION_DRAFTING_PROMPT = """
**You are a world class Patent Specification Drafter. The best in the field.**

Your task is to generate a comprehensive, high-quality **FINAL** descriptive patent specification based on the user-provided invention disclosure. Your goal is to create a document that is clear, technically detailed, well-structured, and provides a strong foundation **from which patent claims could be drafted**. Adhere strictly to standard patent drafting conventions and terminology for the descriptive sections.

**Input:** You will receive:
1.  A detailed description of the invention from the user (sections like Title, Field, Background, Summary, Detailed Description, Advantages, Alternatives).
2.  (Optional) An example patent specification provided by the user whose style should be emulated.

**Style Guidance (If Example Provided):** If an example specification is provided in the context, analyze its writing style, tone, section structure (e.g., use of headings/subheadings), paragraph length, sentence structure, and terminology usage. Apply this analyzed style consistently throughout the generated draft for the new invention's descriptive sections.

**Output Requirements:**

1.  **Structure:** Generate the descriptive specification with the following standard sections, clearly delineated using Markdown headings (`##` for main sections, `###` for subsections). If an example spec is provided, try to mirror its structural nuances where appropriate:
    *   **## TITLE OF THE INVENTION:** Descriptive title. Base it on user input if provided, otherwise create one.
    *   **## BACKGROUND OF THE INVENTION:**
        *   **### Field of the Invention:** Briefly state the technical field based on user input or inference.
        *   **### Description of Related Art:** Discuss existing solutions (prior art mentioned by the user or generally known problems), their limitations, and the problems the current invention aims to solve, based on user input. Frame the problem effectively.
    *   **## SUMMARY OF THE INVENTION:** Provide a brief overview of the invention, highlighting its main aspects, objects, and advantages over the prior art (drawing from user input). Briefly introduce the core concepts that *could* form the basis of claims.
    *   **## DETAILED DESCRIPTION OF THE PREFERRED EMBODIMENT(S):**
        *   This is the core section. Elaborate extensively based **primarily on the user's Detailed Description input**, supplementing with information from Advantages and Alternatives sections.
        *   Describe the structure, components, materials, connections, and operation of the invention in detail. Use placeholder reference numerals (e.g., component 10, step 20) consistently if helpful for clarity. Reference potential drawing figures where appropriate (e.g., "Referring to FIG. 1," "element 12 connects to element 14"), even though a separate drawing list section is not generated here.
        *   Explain *how* the invention solves the problems identified in the Background, linking features to advantages mentioned by the user.
        *   Describe various alternative embodiments, variations, optional features, different materials, use cases, and configurations mentioned by the user. Use broad and encompassing language.
        *   Ensure the description provides enough detail to theoretically enable a Person Having Ordinary Skill In The Art (PHOSITA) to make and use the invention and provides clear support for potential future claims covering the described features and variations.
        *   Clearly link the described features to the advantages of the invention.
    *   **## ABSTRACT OF THE DISCLOSURE:** A summary (typically under 150 words) of the invention's primary features and purpose, allowing readers to quickly grasp the technical disclosure.

2.  **Style and Tone:**
    *   Formal, objective, and precise technical language.
    *   Use consistent terminology.
    *   **If an example spec style is provided, emulate its tone and stylistic choices for the descriptive text.**
    *   Avoid marketing language or subjective statements. Focus on technical facts.
    *   Use Markdown for clear structure and readability.

3.  **Content Generation:**
    *   Synthesize the user's input effectively into the appropriate descriptive sections.
    *   Where the user describes variations, ensure these are captured in the Detailed Description to provide basis for potential claims covering them.
    *   Identify the core inventive concepts from the user's input and focus the Summary around them.
    *   Infer logical connections and operational steps if not explicitly stated but clearly implied by the description.

**Constraint Checklist & Confidence Score:**
After the main specification, append the following section:

---
**Constraint Checklist & Confidence Score:**
*   Constraint Checklist:
    1.  Generated Title: [Yes/No]
    2.  Generated Background (Field & Related Art): [Yes/No]
    3.  Generated Summary: [Yes/No]
    4.  Generated Detailed Description (with enablement/support focus): [Yes/No]
    5.  Generated Abstract: [Yes/No]
    6.  Formal Tone & Style: [Yes/No]
    7.  Description Provides Basis for Claims: [Brief assessment - e.g., "Appears consistent," "Requires review for breadth"]
*   Confidence Score (1-5): [Score reflecting how well the user input allowed fulfilling the descriptive requirements, 5 being best]
*   Key Assumptions or Areas Needing Clarification: [List any major assumptions made or areas where user input was ambiguous/lacking for description]

---
**IMPORTANT:** Do not include any introductory remarks, conversational text, commentary, or preamble before starting the specification draft. Begin the output *directly* with the `## TITLE OF THE INVENTION:` section.
---

**Begin generation upon receiving user input context.**
"""

def generate_specification(job_id: str, **kwargs):
    """
    Generates a draft patent specification using the Gemini API.

    Args:
        job_id (str): Identifier for the job.
        **kwargs: Dictionary containing user inputs (e.g., proposed_title, 
                  field_of_invention, background_problem, summary_idea, 
                  detailed_description, advantages, alternative_embodiments).
                  Expected keys match form field names in spec_app.py.
    Returns:
        str: The generated specification in Markdown format, or an error message.
    """
    print(f"Starting specification generation for Job ID: {job_id}")

    # --- Format User Input for Context ---
    user_context = "## User-Provided Invention Disclosure:\n\n"
    input_map = {
        'proposed_title': 'Proposed Title',
        'field_of_invention': 'Field of the Invention',
        'background_problem': 'Background / Problem',
        'summary_idea': 'Summary of the Invention (Core Idea)',
        'detailed_description': 'Detailed Description of the Invention', # Required field
        'advantages': 'Advantages',
        'alternative_embodiments': 'Alternative Embodiments & Variations',
        'example_spec_style': 'Example Specification Style' # Added example style key
    }
    
    # Check if required field is present
    if not kwargs.get('detailed_description'):
        return "# Error\n\nMissing required field: Detailed Description of the Invention."

    has_example_style = False
    for key, label in input_map.items():
        value = kwargs.get(key)
        if value:
            # Prepend marker for the example style text for clarity in context
            if key == 'example_spec_style':
                user_context += f"\n---\n## Example Specification Style (To Emulate):\n```\n{value}\n```\n\n---\n"
                has_example_style = True
            else:
                user_context += f"### {label}:\n{value}\n\n"
        elif key not in ['detailed_description', 'example_spec_style']: 
             user_context += f"### {label}:\n(Not provided by user)\n\n"
             
    user_context += "\n---\n*End of User-Provided Disclosure*\n"
    if not has_example_style:
         user_context += "\n*(No example specification style was provided by the user.)*\n"

    # --- Call LLM ---
    print(f"Sending request to LLM for Job ID: {job_id}")
    generated_spec = call_gemini_with_retry(
        prompt=SPECIFICATION_DRAFTING_PROMPT,
        context_text=user_context,
        task_description=f"Patent Specification Drafting (Job {job_id})"
    )

    print(f"LLM call finished for Job ID: {job_id}")
    return generated_spec

# --- Example Usage (for testing) ---
if __name__ == '__main__':
    print("Testing patent_generator.py...")
    # Example inputs (replace with actual test data)
    test_inputs = {
        'proposed_title': 'Self-Heating Coffee Mug',
        'field_of_invention': 'Beverage containers',
        'background_problem': 'Coffee gets cold too quickly. Existing travel mugs only insulate, they dont reheat. Battery powered ones are bulky.',
        'summary_idea': 'A mug with an integrated, thin-film resistive heating element powered by a small rechargeable battery in the base, activated by a pressure sensor when the mug is lifted.',
        'detailed_description': 'The mug body (10) is made of stainless steel with vacuum insulation. A thin-film resistive heating element (20) is laminated to the inner wall. The base (30) houses a compact lithium-ion battery (32) and control circuitry (34). A pressure sensor (36) in the base detects when the mug is lifted. When lifted and the temperature is below a threshold, the circuit (34) activates the element (20).',
        'advantages': 'Keeps coffee at optimal temperature for longer without external power. Slim design compared to bulky battery mugs. Automatic activation is convenient.',
        'alternative_embodiments': 'Could use phase change material for passive heating assist. Different activation methods possible (button, timer). Could be integrated with Bluetooth for temperature control via app.',
        'example_spec_style': 'Example Specification Style'
    }
    
    # Ensure API key is loaded for testing
    if not GEMINI_API_KEY:
        print("Cannot run test: GOOGLE_API_KEY not found.")
    else:
        test_spec = generate_specification("test-job-001", **test_inputs)
        print("\n--- Generated Specification (Test) ---")
        print(test_spec)
        print("--- End of Test ---") 