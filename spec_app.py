from flask import Flask, request, render_template, flash, redirect, url_for
import markdown
import patent_generator # Import the new specification generator
import os
import uuid
import threading
from dotenv import load_dotenv
import traceback

load_dotenv() # Load GOOGLE_API_KEY 

app = Flask(__name__) # Needs templates folder
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24)) # Use same secret or generate new

# Simple in-memory storage for job status and results
spec_job_results = {}

def run_spec_generation_in_background(job_id, form_data):
    """Worker function to run specification generation and store result."""
    print(f"Starting background specification job: {job_id}")
    report = ""
    try:
        # Pass job_id and the dictionary of form data
        report = patent_generator.generate_specification(job_id, **form_data)
        if not report:
             report = "# Error\nProcessing completed, but no specification was generated. Check console logs for errors."
        print(f"Background specification job {job_id} finished successfully.")
    except Exception as e:
        print(f"Error in background specification job {job_id}: {e}")
        print(traceback.format_exc()) # Print full traceback for worker errors
        report = f"# Error\n\nAn unexpected error occurred during specification generation: {e}\n\n```\n{traceback.format_exc()}\n```"
    finally:
        spec_job_results[job_id] = report

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Collect all form data into a dictionary
        form_data = {
            'proposed_title': request.form.get('proposed_title'),
            'field_of_invention': request.form.get('field_of_invention'),
            'background_problem': request.form.get('background_problem'),
            'summary_idea': request.form.get('summary_idea'),
            'detailed_description': request.form.get('detailed_description'), # Required
            'advantages': request.form.get('advantages'),
            'alternative_embodiments': request.form.get('alternative_embodiments'),
            'example_spec_style': request.form.get('example_spec_style') # Get the example style
        }

        # Basic validation for the required field
        if not form_data['detailed_description']:
            flash('Please provide the Detailed Description of the Invention.', 'error')
            # Pass back the data the user already entered
            return render_template('spec_index.html', form_data=form_data)

        job_id = str(uuid.uuid4())
        spec_job_results[job_id] = 'processing'

        # Pass the whole form_data dictionary (including example_spec_style) to the background task
        thread = threading.Thread(target=run_spec_generation_in_background, args=(job_id, form_data))
        thread.start()

        return redirect(url_for('result', job_id=job_id))

    # GET request: Show empty form (or pass empty dict for consistency)
    return render_template('spec_index.html', form_data={})

@app.route('/result/<job_id>')
def result(job_id):
    report_markdown = spec_job_results.get(job_id, 'not_found')

    if report_markdown == 'processing':
        # Reuse processing template logic, adjust name if needed
        return render_template('spec_processing.html', job_id=job_id) 
    elif report_markdown == 'not_found':
        flash(f'Result for specification job ID {job_id} not found.', 'error')
        return redirect(url_for('index'))
    else:
        # Clean potential code fences (optional, but good practice)
        cleaned_markdown = report_markdown.strip()
        # Remove ```markdown, ```html, or ``` fences if present
        if cleaned_markdown.startswith(("```markdown", "```html", "```")):
             cleaned_markdown = re.sub(r"^```(markdown|html)?\s*\n", "", cleaned_markdown)
        if cleaned_markdown.endswith("\n```"):
             cleaned_markdown = cleaned_markdown[:-4].strip()
             
        # Convert Markdown to HTML
        # Use extensions for better rendering (tables, fenced code)
        report_html = markdown.markdown(cleaned_markdown, extensions=['fenced_code', 'tables'])
        return render_template('spec_result.html', report_html=report_html) 

# --- Template Creation (Similar to kw_app.py) --- 
# Define basic template content strings (can be refined)
INDEX_SPEC_TEMPLATE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Patent Specification Drafter</title>
<style>
    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; background-color: #f8f9fa; }
    h1 { text-align: center; font-weight: 300; margin-bottom: 30px; }
    label { font-weight: 600; display: block; margin-bottom: 5px; margin-top: 15px; }
    input[type=text], textarea { width: 98%; padding: 10px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 0.95rem; }
    textarea { min-height: 100px; }
    textarea#detailed_description { min-height: 250px; /* Make required field larger */ }
    .optional-label::after { content: " (Optional)"; font-weight: normal; color: #555; font-size: 0.9em; }
    button { background-color: #007bff; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 1rem; margin-top: 20px; }
    button:hover:not(:disabled) { background-color: #0056b3; }
    button:disabled { background-color: #6c757d; cursor: not-allowed; }
    .form-container { background-color: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
    .flash { padding: 1rem; margin-bottom: 1.5rem; border: 1px solid transparent; border-radius: .25rem; }
    .flash.error { color: #721c24; background-color: #f8d7da; border-color: #f5c6cb; }
    .spinner { display: none; /* Similar to kw_app */ }
</style>
</head><body>
<h1>Patent Specification Drafter</h1>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for category, message in messages %}
      <div class="flash {{ category }}">{{ message }}</div>
    {% endfor %}
  {% endif %}
{% endwith %}
<div class="form-container">
  <form id="specForm" method="post">
    <label for="proposed_title" class="optional-label">Proposed Title</label>
    <input type="text" id="proposed_title" name="proposed_title" value="{{ form_data.get('proposed_title', '') }}">

    <label for="field_of_invention" class="optional-label">Field of the Invention</label>
    <input type="text" id="field_of_invention" name="field_of_invention" placeholder="e.g., semiconductor manufacturing, medical devices" value="{{ form_data.get('field_of_invention', '') }}">

    <label for="background_problem" class="optional-label">Background / Problem</label>
    <textarea id="background_problem" name="background_problem" placeholder="Problem solved? Existing solutions & their drawbacks?">{{ form_data.get('background_problem', '') }}</textarea>

    <label for="summary_idea" class="optional-label">Summary of the Invention (Core Idea)</label>
    <textarea id="summary_idea" name="summary_idea" placeholder="Briefly, what is the invention? Key mechanism?">{{ form_data.get('summary_idea', '') }}</textarea>

    <label for="detailed_description">Detailed Description of the Invention <span style="color:red; font-weight:bold;">*</span></label>
    <textarea id="detailed_description" name="detailed_description" required placeholder="MOST CRITICAL PART. Be specific. Structure/Components? Operation/Function? Novel Features? Link to advantages.">{{ form_data.get('detailed_description', '') }}</textarea>

    <label for="advantages" class="optional-label">Advantages</label>
    <textarea id="advantages" name="advantages" placeholder="Specific benefits over prior art? (e.g., faster, cheaper, more efficient)">{{ form_data.get('advantages', '') }}</textarea>

    <label for="alternative_embodiments" class="optional-label">Alternative Embodiments & Variations</label>
    <textarea id="alternative_embodiments" name="alternative_embodiments" placeholder="Other materials? Shapes? Configurations? Use cases? Optional features?">{{ form_data.get('alternative_embodiments', '') }}</textarea>

    <button type="submit" id="submitBtn">Draft Specification</button>
    <div class="spinner" id="loadingSpinner"></div>
  </form>
</div>
<script>
    // Basic script to disable button on submit (similar to kw_app)
    document.getElementById('specForm').addEventListener('submit', function() {
        document.getElementById('submitBtn').disabled = true;
        document.getElementById('submitBtn').textContent = 'Drafting...';
        // Optional: show spinner
    });
</script>
</body></html>
"""

PROCESSING_SPEC_TEMPLATE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="10"><title>Drafting Specification...</title>
<style>body { font-family: sans-serif; max-width: 600px; margin: 100px auto; text-align: center; } .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #007bff; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; } @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } } .note { font-size: 0.9em; color: #555; margin-top: 30px; }</style>
</head><body><h1>Drafting Patent Specification</h1><div class="spinner"></div><p>Your invention disclosure is being processed by the AI drafter.</p><p>This page will refresh automatically. Please wait...</p>
<p class="note"><b>Note:</b> Specification drafting is complex and may take several minutes.</p>
<p>(Job ID: {{ job_id }})</p></body></html>
"""

RESULT_SPEC_TEMPLATE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Draft Specification Result</title>
<style>body { font-family: sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; line-height: 1.6; } h1 { font-weight: 300; text-align: center; } h2 { border-bottom: 1px solid #ccc; padding-bottom: 0.3em; margin-top: 2em; } h3 { margin-top: 1.5em; font-weight: 600; } .report-content { background-color: #fff; padding: 25px; border: 1px solid #ddd; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-top: 20px; } code { background-color: #f1f1f1; padding: 0.2em 0.4em; border-radius: 3px; } pre { background-color: #f1f1f1; border: 1px solid #ddd; border-radius: 4px; padding: 10px; overflow-x: auto; } .back-link { display: block; text-align: center; margin-top: 30px; font-size: 1.1rem; }</style>
</head><body><h1>Draft Patent Specification</h1>
<div class="report-content">{{ report_html|safe }}</div>
<div class="back-link"><a href="/">Draft Another Specification</a></div>
</body></html>
"""

def create_template_if_not_exists(path, content):
     if not os.path.exists(path):
         try:
             with open(path, 'w', encoding='utf-8') as f:
                  f.write(content)
             print(f"Created template: {path}")
         except Exception as e:
             print(f"Error creating template {path}: {e}")

if __name__ == '__main__':
    # Ensure templates directory exists
    if not os.path.exists('templates'):
        try:
            os.makedirs('templates')
            print("Created 'templates' directory.")
        except Exception as e:
            print(f"Error creating 'templates' directory: {e}")
            # Exit if we can't create templates dir?
            # sys.exit(1) 
        
    # Create templates using the new names/content
    create_template_if_not_exists('templates/spec_index.html', INDEX_SPEC_TEMPLATE)
    create_template_if_not_exists('templates/spec_processing.html', PROCESSING_SPEC_TEMPLATE)
    create_template_if_not_exists('templates/spec_result.html', RESULT_SPEC_TEMPLATE)
         
    print("Running Patent Specification Drafting App...")
    # Run on a different port (e.g., 5002)
    app.run(debug=True, port=5002, threaded=True) 