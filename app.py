from flask import Flask, request, render_template, flash, redirect, url_for, session
import markdown
import patent_classifier # Import the refactored classification script
import os
import uuid # To generate unique IDs for processing jobs
import threading # To run classification in background
from dotenv import load_dotenv

load_dotenv() # Load GOOGLE_API_KEY from .env

app = Flask(__name__) # Needs templates folder
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24)) # Use env var or random

# Define the temporary file path for the spec (might not be needed if passing text directly)
TEMP_SPEC_FILE = "spec.txt"

# Simple in-memory storage for job status and results (replace with DB/Redis for production)
job_results = {}

def run_classification_in_background(job_id, patent_text):
    """Worker function to run classification and store result."""
    print(f"Starting background job: {job_id}")
    report = ""
    try:
        # Ensure the necessary directories exist relative to this script
        if not os.path.isdir("pdfs/schemes") or not os.path.isdir("pdfs/definitions"):
             raise FileNotFoundError("Required directories 'pdfs/schemes' or 'pdfs/definitions' not found.")
        
        # Call the function from the imported module
        report = patent_classifier.run_classification_process(patent_text)
        if not report:
             report = "Processing completed, but no report was generated. Check console logs."
        print(f"Background job {job_id} finished successfully.")
    except Exception as e:
        print(f"Error in background job {job_id}: {e}")
        # Consider adding traceback logging here
        report = f"# Error\n\nAn unexpected error occurred during processing: {e}"
    finally:
        # Store result (even if error)
        job_results[job_id] = report

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        patent_text = request.form.get('patent_spec')
        if not patent_text:
            flash('Please paste the patent specification text.', 'error')
            return render_template('index.html')

        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        job_results[job_id] = 'processing' # Mark as processing

        # Start classification in a background thread
        thread = threading.Thread(target=run_classification_in_background, args=(job_id, patent_text))
        thread.start()

        # Redirect to the results page, passing the job ID
        return redirect(url_for('result', job_id=job_id))

    # GET request: just show the main page
    # Read content from spec.txt to pre-populate the textarea
    existing_spec = ""
    if os.path.exists(TEMP_SPEC_FILE): # Use the constant defined earlier
        try:
            with open(TEMP_SPEC_FILE, 'r') as f:
                existing_spec = f.read()
                print(f"Pre-populated text area from {TEMP_SPEC_FILE}")
        except Exception as e:
             print(f"Could not read existing {TEMP_SPEC_FILE} for pre-population: {e}")
             
    return render_template('index.html', current_spec=existing_spec)

@app.route('/result/<job_id>')
def result(job_id):
    """Page to display results or check status."""
    report_markdown = job_results.get(job_id, 'not_found')

    if report_markdown == 'processing':
        # Job is still running, render a page that auto-refreshes or waits
        return render_template('processing.html', job_id=job_id)
    elif report_markdown == 'not_found':
        flash(f'Result for job ID {job_id} not found.', 'error')
        return redirect(url_for('index'))
    else:
        # Job finished (or errored), clean up and display result
        # Optional: Remove job from memory after retrieval
        # del job_results[job_id] 

        # --- Clean potential code fences from Gemini response --- 
        cleaned_markdown = report_markdown.strip()
        if cleaned_markdown.startswith("```markdown"):
             cleaned_markdown = cleaned_markdown[len("```markdown"):].strip()
        elif cleaned_markdown.startswith("```html"):
             cleaned_markdown = cleaned_markdown[len("```html"):].strip()
        elif cleaned_markdown.startswith("```"):
             cleaned_markdown = cleaned_markdown[3:].strip()
        if cleaned_markdown.endswith("```"):
             cleaned_markdown = cleaned_markdown[:-3].strip()
        # -----------------------------------------------------

        # Convert cleaned report Markdown to HTML
        report_html = markdown.markdown(cleaned_markdown, extensions=['fenced_code', 'tables'])

        # Render the result template
        return render_template('result.html', report_html=report_html)

# Need a simple processing template
PROCESSING_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="10"> <!-- Refresh every 10 seconds -->
    <title>Processing...</title>
    <style>
        body { font-family: sans-serif; max-width: 600px; margin: 100px auto; text-align: center; }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <h1>Processing Patent Classification</h1>
    <div class="spinner"></div>
    <p>Your request is being processed. This page will automatically refresh. Please wait...</p>
    <p>(Job ID: {{ job_id }})</p>
</body>
</html>
"""

if __name__ == '__main__':
    # Ensure templates directory exists
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("Created 'templates' directory.")
    # Check/create template files if they don't exist (basic versions)
    # index.html and result.html should exist, create processing.html
    if not os.path.exists('templates/processing.html'):
         with open('templates/processing.html', 'w') as f:
              f.write(PROCESSING_TEMPLATE)
         print("Created basic 'templates/processing.html'.")
         
    app.run(debug=True, threaded=True) # Use threaded mode for background tasks 