import os
import json
import uuid
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from tempfile import NamedTemporaryFile
from django.template.loader import get_template
from xhtml2pdf import pisa
from .nlp_processor import extract_text_from_pdf, extract_text_from_docx
import openai
from functools import lru_cache


analysis_results = {}

openai.api_key = "..."

def index(request):
    """Home page view"""
    return render(request, 'analyzer/index.html')

@lru_cache(maxsize=100)  # Cache up to 100 results to optimize API calls
def analyze_resume_job_match_cached(resume_text, job_text):
    return analyze_resume_job_match(resume_text, job_text)

def upload_and_analyze(request):
    """Handle file uploads and analysis using OpenAI API, and prepare interactive chart data."""
    if request.method == 'POST':
        resume_file = request.FILES.get('resume')
        if not resume_file:
            return JsonResponse({'error': 'No resume file provided'}, status=400)

        job_description_text = request.POST.get('job_description', '')
        if not job_description_text:
            return JsonResponse({'error': 'No job description provided'}, status=400)

        # Save uploaded file temporarily
        suffix = ".pdf" if resume_file.name.lower().endswith('.pdf') else ".docx"
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            for chunk in resume_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        # Extract text based on file type
        if temp_file_path.endswith('.pdf'):
            resume_text = extract_text_from_pdf(temp_file_path)
        elif temp_file_path.endswith('.docx') or temp_file_path.endswith('.doc'):
            resume_text = extract_text_from_docx(temp_file_path)
        else:
            os.remove(temp_file_path)
            return JsonResponse({'error': 'Unsupported file format. Please use PDF or DOCX'}, status=400)

        # Delete temporary file after processing
        os.remove(temp_file_path)

        # Analyze the match using OpenAI API
        analysis  = analyze_resume_job_match_cached(resume_text, job_description_text)

        # Prepare interactive chart data for Chart.js
        chart_data = prepare_chart_data(analysis)

        # Generate a unique ID for this analysis
        analysis_id = str(uuid.uuid4())

        # Store the result in memory
        analysis_results[analysis_id] = {
            'job_description': job_description_text,
            'analysis': analysis,
            'chart_data': chart_data
        }

        context = {
            'job_description': job_description_text,
            'analysis': analysis,
            'chart_data': chart_data,
            'analysis_id': analysis_id
        }

        return render(request, 'analyzer/results.html', context)

    return render(request, 'analyzer/index.html')

def analyze_resume_job_match(resume_text, job_text):
    
    prompt = f"""
    You are an AI that evaluates how well a resume matches a job description.
    Analyze the given resume and job description to provide a comprehensive match analysis.
    
    Requirements for JSON response:
    - match_percentage: Overall match score (0-100%)
    - matched_skills: List of skills found in the resume
    - missing_skills: List of skills not found in the resume
    - skill_match_percentage: Percentage of required skills matched
    - semantic_match_percentage: Content relevance percentage
    - summary: Brief overview of the match
    - recommendations: List of suggestions to improve resume
    - contact_info: Dictionary with name, email, phone (if available)

    Format your response as a valid JSON object.

    Resume:
    {resume_text}

    Job Description:
    {job_text}
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are an AI resume-job matching expert. Always respond in a valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )
        
        # Extract the content from the response
        result = response["choices"][0]["message"]["content"].strip()
        
        # Try to parse the JSON, with error handling
        try:
            # Remove any leading/trailing code block markers
            if result.startswith('```json'):
                result = result[7:]
            if result.endswith('```'):
                result = result[:-3]
            
            # Parse the JSON
            analysis = json.loads(result)
            
            # Ensure all required keys exist
            required_keys = [
                'match_percentage', 'matched_skills', 'missing_skills', 
                'skill_match_percentage', 'semantic_match_percentage', 
                'summary', 'recommendations', 'contact_info'
            ]
            for key in required_keys:
                if key not in analysis:
                    analysis[key] = [] if 'skills' in key or key == 'recommendations' else '' if key == 'summary' else 0
            
            return analysis
        
        except json.JSONDecodeError as json_error:
            # Log the actual response for debugging
            print(f"JSON Parsing Error: {json_error}")
            print(f"Problematic Response: {result}")
            return {
                "error": f"Error parsing OpenAI API response: {json_error}",
                "raw_response": result,
                "match_percentage": 0,
                "matched_skills": [],
                "missing_skills": [],
                "skill_match_percentage": 0,
                "semantic_match_percentage": 0,
                "summary": "Unable to parse analysis results.",
                "recommendations": [],
                "contact_info": {}
            }
    
    except Exception as e:
        # Handle any other unexpected errors
        return {
            "error": f"OpenAI API error: {str(e)}",
            "match_percentage": 0,
            "matched_skills": [],
            "missing_skills": [],
            "skill_match_percentage": 0,
            "semantic_match_percentage": 0,
            "summary": "An unexpected error occurred during analysis.",
            "recommendations": [],
            "contact_info": {}
        }

def prepare_chart_data(analysis):
    """
    Prepare chart data for interactive Chart.js rendering.
    Three charts are prepared:
      1. A donut chart for overall match percentage.
      2. A bar chart for skills (matched vs. missing).
      3. A bar chart for match types: skill_match_percentage, semantic_match_percentage, overall match_percentage.
    """
    return {
        'gauge': {
            'match_percentage': analysis.get('match_percentage', 0)
        },
        'skills': {
            'matched': len(analysis.get('matched_skills', [])),
            'missing': len(analysis.get('missing_skills', []))
        },
        'match_types': {
            'skill_match': analysis.get('skill_match_percentage', 0),
            'semantic_match': analysis.get('semantic_match_percentage', 0),
            'overall_match': analysis.get('match_percentage', 0)
        }
    }

def view_result(request, analysis_id):
    """View a specific analysis result from in-memory storage"""
    if analysis_id not in analysis_results:
        return render(request, 'analyzer/index.html')

    stored_result = analysis_results[analysis_id]
    context = {
        'job_description': stored_result['job_description'],
        'analysis': stored_result['analysis'],
        'chart_data': stored_result['chart_data'],
        'analysis_id': analysis_id
    }
    return render(request, 'analyzer/results.html', context)

def download_pdf(request, analysis_id):
    """Download analysis result as a PDF file"""
    if analysis_id not in analysis_results:
        return render(request, 'analyzer/index.html')

    stored_result = analysis_results[analysis_id]
    context = {
        'job_description': stored_result['job_description'],
        'analysis': stored_result['analysis'],
        'chart_data': stored_result['chart_data'],
        'analysis_id': analysis_id
    }

    template = get_template('analyzer/results_pdf.html')
    html = template.render(context)
    from io import BytesIO
    result = BytesIO()
    pdf = pisa.CreatePDF(BytesIO(html.encode("UTF-8")), dest=result)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="resume_analysis_{analysis_id}.pdf"'
        return response
    return HttpResponse("Error generating PDF", status=400)

def bot_question(request):
    """
    Handle bot questions about the resume analysis
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            analysis_id = data.get('analysis_id')
            question = data.get('question')

            # Retrieve the stored analysis
            if analysis_id not in analysis_results:
                return JsonResponse({'error': 'Analysis not found'}, status=404)

            stored_result = analysis_results[analysis_id]
            job_description = stored_result['job_description']
            analysis = stored_result['analysis']

            # Prepare detailed prompt for OpenAI
            prompt = f"""
            You are an AI HR assistant helping to evaluate a job candidate's resume.

            Context:
            - Job Description: {job_description}
            - Resume Analysis:
              * Overall Match: {analysis.get('match_percentage', 0)}%
              * Skills Match: {analysis.get('skill_match_percentage', 0)}%
              * Semantic Match: {analysis.get('semantic_match_percentage', 0)}%
              * Matched Skills: {', '.join(analysis.get('matched_skills', []))}
              * Missing Skills: {', '.join(analysis.get('missing_skills', []))}

            Candidate Question: {question}

            Provide a short and concise, professional, and insightful response highlighting that helps an HR professional understand the candidate's fit.
            """

            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4-turbo",
                    messages=[
                        {"role": "system", "content": "You are an AI HR assistant providing expert insights on candidate evaluation."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=300,
                    temperature=0.7
                )
                
                bot_response = response['choices'][0]['message']['content'].strip()
                
                return JsonResponse({
                    'response': bot_response
                })
            
            except Exception as api_error:
                return JsonResponse({
                    'error': f'OpenAI API error: {str(api_error)}',
                    'details': str(api_error)
                }, status=500)
        
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


def prepare_comparison_chart_data(resume_analyses):
    """Prepare chart data for comparing multiple resumes"""
    # Extract labels (file names) and data points
    labels = [analysis.get('file_name', f"Resume {i+1}") for i, analysis in enumerate(resume_analyses)]
    
    # Data for overall match percentage
    match_percentages = [analysis.get('match_percentage', 0) for analysis in resume_analyses]
    
    # Data for skill match percentage
    skill_match_percentages = [analysis.get('skill_match_percentage', 0) for analysis in resume_analyses]
    
    # Data for semantic match percentage
    semantic_match_percentages = [analysis.get('semantic_match_percentage', 0) for analysis in resume_analyses]
    
    # Count of matched and missing skills
    matched_skills_counts = [len(analysis.get('matched_skills', [])) for analysis in resume_analyses]
    missing_skills_counts = [len(analysis.get('missing_skills', [])) for analysis in resume_analyses]
    
    # Common skills across all resumes
    all_matched_skills = [set(analysis.get('matched_skills', [])) for analysis in resume_analyses]
    if all_matched_skills:
        common_skills = set.intersection(*all_matched_skills) if all_matched_skills else set()
        common_skills_list = list(common_skills)
    else:
        common_skills_list = []
    
    # Unique skills by each resume
    unique_skills_by_resume = []
    for i, analysis in enumerate(resume_analyses):
        matched_skills_set = set(analysis.get('matched_skills', []))
        other_skills_sets = [set(other.get('matched_skills', [])) for j, other in enumerate(resume_analyses) if j != i]
        other_skills = set.union(*other_skills_sets) if other_skills_sets else set()
        unique_skills = matched_skills_set - other_skills
        unique_skills_by_resume.append(list(unique_skills))
    
    # Return structured chart data as a serializable dictionary
    return {
        'labels': labels,
        'match_percentages': match_percentages,
        'skill_match_percentages': skill_match_percentages,
        'semantic_match_percentages': semantic_match_percentages,
        'matched_skills_counts': matched_skills_counts,
        'missing_skills_counts': missing_skills_counts,
        'common_skills': common_skills_list,
        'unique_skills_by_resume': unique_skills_by_resume
    }

def compare_resumes(request):
    """View for comparing multiple resumes against a job description"""
    if request.method == 'POST':
        # Get uploaded files
        resume_files = request.FILES.getlist('resumes')
        job_description_text = request.POST.get('job_description', '')
        
        if not resume_files:
            return render(request, 'analyzer/compare_form.html', {'error': 'No resume files provided'})
        
        if len(resume_files) < 2:
            return render(request, 'analyzer/compare_form.html', {'error': 'Please upload at least two resumes for comparison'})
        
        if not job_description_text:
            return render(request, 'analyzer/compare_form.html', {'error': 'No job description provided'})
        
        # Process each resume file
        resume_analyses = []
        for idx, resume_file in enumerate(resume_files):
            # Save uploaded file temporarily
            suffix = ".pdf" if resume_file.name.lower().endswith('.pdf') else ".docx"
            with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                for chunk in resume_file.chunks():
                    temp_file.write(chunk)
                temp_file_path = temp_file.name
            
            # Extract text based on file type
            if temp_file_path.endswith('.pdf'):
                resume_text = extract_text_from_pdf(temp_file_path)
            elif temp_file_path.endswith('.docx') or temp_file_path.endswith('.doc'):
                resume_text = extract_text_from_docx(temp_file_path)
            else:
                os.remove(temp_file_path)
                continue  # Skip unsupported file formats
            
            # Delete temporary file after processing
            os.remove(temp_file_path)
            
            # Analyze the match using OpenAI API
            analysis = analyze_resume_job_match_cached(resume_text, job_description_text)
            
            # Add resume file name and index information
            analysis['file_name'] = resume_file.name
            analysis['index'] = idx + 1
            
            resume_analyses.append(analysis)
        
        # Sort analyses by match percentage (descending)
        resume_analyses.sort(key=lambda x: x.get('match_percentage', 0), reverse=True)
        
        # Generate comparative insights using OpenAI
        comparative_insights = generate_comparative_insights(resume_analyses, job_description_text)
        
        # Generate chart data for comparison
        comparison_chart_data = prepare_comparison_chart_data(resume_analyses)
        
        # Generate a unique ID for this multi-resume analysis
        analysis_id = str(uuid.uuid4())
        
        # Store the result in memory
        analysis_results[analysis_id] = {
            'job_description': job_description_text,
            'analyses': resume_analyses,
            'comparative_insights': comparative_insights,
            'chart_data': comparison_chart_data
        }
        
        # Convert chart_data to JSON string for template
        import json
        chart_data_json = json.dumps(comparison_chart_data)
        
        context = {
            'job_description': job_description_text,
            'analyses': resume_analyses,
            'comparative_insights': comparative_insights,
            'chart_data': chart_data_json,
            'analysis_id': analysis_id
        }
        
        return render(request, 'analyzer/compare_results.html', context)
    
    return render(request, 'analyzer/compare_form.html')

def generate_comparative_insights(resume_analyses, job_description):
    """Generate comparative insights for multiple resumes using OpenAI"""
    try:
        # Prepare data for the prompt
        resume_data = []
        for idx, analysis in enumerate(resume_analyses):
            resume_data.append({
                "index": idx + 1,
                "file_name": analysis.get('file_name', f"Resume {idx+1}"),
                "match_percentage": analysis.get('match_percentage', 0),
                "skill_match_percentage": analysis.get('skill_match_percentage', 0),
                "matched_skills": analysis.get('matched_skills', []),
                "missing_skills": analysis.get('missing_skills', [])
            })
        
        prompt = f"""
        You are an AI HR assistant analyzing multiple resumes for a job opening.
        
        Job Description:
        {job_description}
        
        Resume Analysis Results:
        {json.dumps(resume_data, indent=2)}
        
        Please provide:
        1. A comparative analysis highlighting the strengths and weaknesses of each candidate
        2. Key differentiating factors between the candidates
        3. How each candidate matches specific aspects of the job description
        4. Suggestions for which candidate(s) should be prioritized for interviews and why
        
        Format your response as a valid JSON object with these keys:
        - overall_comparison: Text summary comparing all candidates
        - top_candidate_analysis: Analysis of why the top-ranked candidate stands out
        - interview_recommendations: Ordered list of which candidates to interview first with rationale
        - skill_distribution: Text describing how key skills are distributed across candidates
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are an AI HR assistant providing comparative analysis of job candidates. Always respond in valid JSON format."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        # Extract the content from the response
        result = response["choices"][0]["message"]["content"].strip()
        
        # Try to parse the JSON
        try:
            # Remove any code block markers
            if result.startswith('```json'):
                result = result[7:]
            if result.endswith('```'):
                result = result[:-3]
            
            # Parse the JSON
            insights = json.loads(result)
            
            # Ensure all required keys exist
            required_keys = ['overall_comparison', 'top_candidate_analysis', 'interview_recommendations', 'skill_distribution']
            for key in required_keys:
                if key not in insights:
                    insights[key] = "Analysis not available for this section."
            
            return insights
        
        except json.JSONDecodeError as json_error:
            return {
                "error": f"Error parsing OpenAI API response: {json_error}",
                "overall_comparison": "Unable to generate comparative analysis.",
                "top_candidate_analysis": "Analysis not available.",
                "interview_recommendations": "Recommendations not available.",
                "skill_distribution": "Skill distribution analysis not available."
            }
    
    except Exception as e:
        return {
            "error": f"OpenAI API error: {str(e)}",
            "overall_comparison": "Unable to generate comparative analysis due to an error.",
            "top_candidate_analysis": "Analysis not available due to an error.",
            "interview_recommendations": "Recommendations not available due to an error.",
            "skill_distribution": "Skill distribution analysis not available due to an error."
        }

