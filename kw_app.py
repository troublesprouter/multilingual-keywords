from flask import Flask, request, render_template, flash, redirect, url_for
import markdown
import keyword_generator # Import the new keyword generator script
import os
import uuid
import threading
from dotenv import load_dotenv

load_dotenv() # Load GOOGLE_API_KEY and potentially LOCAL from .env

app = Flask(__name__) # Needs templates folder
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Check if running in local mode
IS_LOCAL = os.environ.get('LOCAL', 'false').lower() == 'true'

# Simple in-memory storage for job status and results
job_results = {}

def run_keyword_generation_in_background(job_id, description_text):
    """Worker function to run keyword generation and store result."""
    print(f"Starting background keyword job: {job_id}")
    report = ""
    try:
        report = keyword_generator.generate_keyword_report(description_text)
        if not report:
             report = "Processing completed, but no keyword report was generated. Check console logs."
        print(f"Background keyword job {job_id} finished successfully.")
    except Exception as e:
        print(f"Error in background keyword job {job_id}: {e}")
        report = f"# Error\n\nAn unexpected error occurred during keyword generation: {e}"
    finally:
        job_results[job_id] = report

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        description_text = request.form.get('invention_description')
        if not description_text:
            flash('Please paste the invention description text.', 'error')
            return render_template('kw_index.html')

        job_id = str(uuid.uuid4())
        job_results[job_id] = 'processing'

        # Pass the description from the form to the background job
        thread = threading.Thread(target=run_keyword_generation_in_background, args=(job_id, description_text))
        thread.start()

        return redirect(url_for('result', job_id=job_id))

    # GET request
    existing_spec = "" # Default to empty
    
    # Only pre-populate if LOCAL=true is set in .env
    if IS_LOCAL:
        print("Local mode detected (LOCAL=true). Attempting to pre-populate from spec.txt...")
        spec_file_path = "spec.txt"
        if os.path.exists(spec_file_path):
            try:
                with open(spec_file_path, 'r', encoding='utf-8') as f: # Specify encoding
                    existing_spec = f.read()
                    print(f"Pre-populated keyword text area from {spec_file_path}")
            except Exception as e:
                 print(f"Could not read existing {spec_file_path} for pre-population: {e}")
        else:
             print(f"spec.txt not found, leaving text area empty.")
    else:
        print("Non-local mode (LOCAL is not 'true'). Text area will be empty by default.")

    # Pass the potentially pre-populated content to the template
    return render_template('kw_index.html', current_spec=existing_spec)

@app.route('/result/<job_id>')
def result(job_id):
    report_markdown = job_results.get(job_id, 'not_found')

    if report_markdown == 'processing':
        return render_template('kw_processing.html', job_id=job_id) # Use new template name
    elif report_markdown == 'not_found':
        flash(f'Result for job ID {job_id} not found.', 'error')
        return redirect(url_for('index'))
    else:
        # Clean potential code fences 
        cleaned_markdown = report_markdown.strip()
        if cleaned_markdown.startswith("```markdown"):
             cleaned_markdown = cleaned_markdown[len("```markdown"):].strip()
        elif cleaned_markdown.startswith("```html"):
             cleaned_markdown = cleaned_markdown[len("```html"):].strip()
        elif cleaned_markdown.startswith("```"):
             cleaned_markdown = cleaned_markdown[3:].strip()
        if cleaned_markdown.endswith("```"):
             cleaned_markdown = cleaned_markdown[:-3].strip()

        report_html = markdown.markdown(cleaned_markdown, extensions=['fenced_code', 'tables'])
        return render_template('kw_result.html', report_html=report_html) # Use new template name

# Templates (basic versions written if not exist)
PROCESSING_KW_TEMPLATE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="5"><title>Generating Keywords...</title><style>body { font-family: sans-serif; max-width: 600px; margin: 100px auto; text-align: center; }.spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style></head><body><h1>Generating Keyword Report</h1><div class="spinner"></div><p>Your request is being processed. This page will refresh automatically. Please wait...</p><p>(Job ID: {{ job_id }})</p></body></html>
"""
INDEX_KW_TEMPLATE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Multilingual Keyword Generator</title><style>body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; background-color: #f8f9fa; color: #343a40; } h1 { color: #212529; text-align: center; margin-bottom: 30px; font-weight: 300; } textarea { width: 98%; padding: 12px; margin-bottom: 15px; border: 1px solid #ced4da; border-radius: 5px; font-size: 0.95rem; min-height: 200px; box-shadow: inset 0 1px 2px rgba(0,0,0,0.075); } textarea:focus { border-color: #80bdff; outline: 0; box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25); } #submitBtn { background-color: #28a745; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 1rem; transition: background-color 0.3s ease; display: inline-block; vertical-align: middle; } #submitBtn:hover:not(:disabled) { background-color: #218838; } #submitBtn:disabled { background-color: #6c757d; cursor: not-allowed; } .flash { padding: 1rem; margin-bottom: 1.5rem; border: 1px solid transparent; border-radius: .25rem; } .flash.error { color: #721c24; background-color: #f8d7da; border-color: #f5c6cb; } .flash.info { color: #004085; background-color: #cce5ff; border-color: #b8daff; } label { font-weight: 600; display: block; margin-bottom: 8px; } .form-container { background-color: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); } .spinner { display: none; border: 3px solid #f3f3f3; border-top: 3px solid #28a745; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; margin-left: 10px; vertical-align: middle; } .helper-text { font-size: 0.85rem; color: #6c757d; margin-top: -10px; margin-bottom: 15px; } @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style></head><body><h1>Multilingual Patent Keyword Generator</h1> {% with messages = get_flashed_messages(with_categories=true) %} {% if messages %} {% for category, message in messages %} <div class="flash {{ category }}">{{ message }}</div> {% endfor %} {% endif %} {% endwith %} <div class="form-container"> <form id="keywordForm" method="post"> <label for="invention_description">Invention Description</label> <textarea id="invention_description" name="invention_description" required placeholder="Paste relevant text describing the invention (abstract, summary, etc.)...">{{ current_spec | default('') }}</textarea> <p class="helper-text">Tip: Provide a clear and detailed description of the invetion or a complete patent. The more detailed the better.</p> <button type="submit" id="submitBtn">Generate Keywords</button> <div class="spinner" id="loadingSpinner"></div> </form> </div> <script>document.getElementById('keywordForm').addEventListener('submit', function() { document.getElementById('submitBtn').disabled = true; document.getElementById('submitBtn').textContent = 'Generating...'; document.getElementById('loadingSpinner').style.display = 'inline-block'; });</script></body></html>
"""
RESULT_KW_TEMPLATE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Keyword Results</title><style>body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; line-height: 1.6; background-color: #f8f9fa; color: #343a40; } h1, h2, h3 { color: #212529; margin-top: 1.5em; margin-bottom: 0.8em; font-weight: 400; } h1 {text-align: center; font-weight: 300;} h2 { border-bottom: 1px solid #dee2e6; padding-bottom: 0.3em;} h3 { font-size: 1.2em; } .report-content { background-color: #fff; padding: 25px; border: 1px solid #ddd; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); } code { background-color: #e9ecef; padding: 0.2em 0.4em; margin: 0; font-size: 85%; border-radius: 3px; } pre { background-color: #e9ecef; border: 1px solid #ced4da; border-radius: 4px; padding: 10px; overflow-x: auto; } pre code { background-color: transparent; padding: 0; } ul, ol { padding-left: 20px; } li { margin-bottom: 0.5em; } table { border-collapse: collapse; width: 100%; margin-bottom: 1rem; } th, td { padding: 0.75rem; vertical-align: top; border-top: 1px solid #dee2e6; text-align: left; } th { background-color: #f1f1f1; } a { color: #007bff; text-decoration: none; } a:hover { text-decoration: underline; } .back-link { display: block; text-align: center; margin-top: 30px; font-size: 1.1rem; }</style></head><body><!-- Title may be included in report_html --> <div class="report-content"> {{ report_html|safe }} </div> <div class="back-link"> <a href="/">Generate Keywords for Another Invention</a> </div></body></html>
"""

def create_template_if_not_exists(path, content):
     if not os.path.exists(path):
         with open(path, 'w') as f:
              f.write(content)
         print(f"Created basic template: {path}")

if __name__ == '__main__':
    # Ensure templates directory exists
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("Created 'templates' directory.")
        
    create_template_if_not_exists('templates/kw_index.html', INDEX_KW_TEMPLATE)
    create_template_if_not_exists('templates/kw_processing.html', PROCESSING_KW_TEMPLATE)
    create_template_if_not_exists('templates/kw_result.html', RESULT_KW_TEMPLATE)
         
    print(f"Running Flask app in {'Local' if IS_LOCAL else 'Non-Local'} mode.")
    app.run(debug=True, port=5001, threaded=True) # Run on a different port (5001) 