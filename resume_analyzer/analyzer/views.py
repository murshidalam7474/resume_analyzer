import os
import json
import uuid
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.core.files.storage import FileSystemStorage
from tempfile import NamedTemporaryFile
import matplotlib.pyplot as plt
import matplotlib
import base64
from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa
from .nlp_processor import (extract_text_from_pdf, extract_text_from_docx, 
                           analyze_resume_job_match)

matplotlib.use('Agg')

# In-memory storage for analysis results
analysis_results = {}

def index(request):
    """Home page view"""
    return render(request, 'analyzer/index.html')

def upload_and_analyze(request):
    """Handle file uploads and analysis without using DB"""
    if request.method == 'POST':
        # Get resume file from request
        resume_file = request.FILES.get('resume')
        if not resume_file:
            return JsonResponse({'error': 'No resume file provided'}, status=400)
        
        # Get job description text
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
        
        # Analyze the match
        analysis = analyze_resume_job_match(resume_text, job_description_text)
        
        # Generate charts for dashboard
        charts = generate_charts(analysis)
        
        # Generate a unique ID for this analysis
        analysis_id = str(uuid.uuid4())
        
        # Store the result in memory
        analysis_results[analysis_id] = {
            # 'job_title': request.POST.get('job_title', 'Untitled Job'),
            'job_description': job_description_text,
            'analysis': analysis
        }
        
        context = {
            # 'job_title': request.POST.get('job_title', 'Untitled Job'),
            'job_description': job_description_text,
            'analysis': analysis,
            'charts': charts,
            'analysis_id': analysis_id
        }
        
        return render(request, 'analyzer/results.html', context)
    
    return render(request, 'analyzer/index.html')

def generate_charts(analysis):
    """Generate charts for the dashboard"""
    charts = {}
    
    # Gauge chart for overall match percentage
    plt.figure(figsize=(8, 4))
    plt.axis('equal')
    match_percentage = analysis['match_percentage']
    sizes = [match_percentage, 100 - match_percentage]
    colors = ['#4CAF50' if match_percentage >= 70 else '#FFC107' if match_percentage >= 50 else '#F44336', '#EEEEEE']
    plt.pie(sizes, colors=colors, startangle=90, counterclock=False)
    circle = plt.Circle((0, 0), 0.7, color='white')
    plt.gcf().gca().add_artist(circle)
    plt.text(0, 0, f"{match_percentage}%", ha='center', va='center', fontsize=24, fontweight='bold')
    plt.title('Overall Match Percentage', fontsize=16)
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    charts['gauge_chart'] = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()
    
    # Skills comparison chart
    matched_skills = analysis['matched_skills']
    missing_skills = analysis['missing_skills']
    if matched_skills or missing_skills:
        plt.figure(figsize=(10, 6))
        data = [len(matched_skills), len(missing_skills)]
        labels = ['Matched Skills', 'Missing Skills']
        colors = ['#4CAF50', '#F44336']
        plt.bar(labels, data, color=colors)
        plt.title('Skills Comparison', fontsize=16)
        plt.ylabel('Number of Skills')
        for i, v in enumerate(data):
            plt.text(i, v + 0.1, str(v), ha='center')
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        charts['skills_chart'] = base64.b64encode(buffer.getvalue()).decode('utf-8')
        plt.close()
    
    # Match types comparison chart
    plt.figure(figsize=(10, 6))
    categories = ['Skills Match', 'Semantic Match', 'Overall Match']
    values = [
        analysis['skill_match_percentage'],
        analysis['semantic_match_percentage'],
        analysis['match_percentage']
    ]
    colors = []
    for value in values:
        if value >= 70:
            colors.append('#4CAF50')
        elif value >= 50:
            colors.append('#FFC107')
        else:
            colors.append('#F44336')
    plt.bar(categories, values, color=colors)
    plt.title('Match Type Comparison', fontsize=16)
    plt.ylabel('Match Percentage (%)')
    plt.ylim(0, 100)
    for i, v in enumerate(values):
        plt.text(i, v + 2, f"{v:.1f}%", ha='center')
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    charts['match_types_chart'] = base64.b64encode(buffer.getvalue()).decode('utf-8')
    plt.close()
    
    return charts

def view_result(request, analysis_id):
    """View a specific analysis result from in-memory storage"""
    if analysis_id not in analysis_results:
        return render(request, 'analyzer/index.html')
    
    stored_result = analysis_results[analysis_id]
    analysis = stored_result['analysis']
    charts = generate_charts(analysis)
    
    context = {
        # 'job_title': stored_result['job_title'],
        'job_description': stored_result['job_description'],
        'analysis': analysis,
        'charts': charts,
        'analysis_id': analysis_id
    }
    
    return render(request, 'analyzer/results.html', context)

def download_pdf(request, analysis_id):
    """Download analysis result as a PDF file"""
    if analysis_id not in analysis_results:
        return render(request, 'analyzer/index.html')
    
    stored_result = analysis_results[analysis_id]
    analysis = stored_result['analysis']
    charts = generate_charts(analysis)
    
    context = {
        # 'job_title': stored_result['job_title'],
        'job_description': stored_result['job_description'],
        'analysis': analysis,
        'charts': charts,
        'analysis_id': analysis_id
    }
    
    template = get_template('analyzer/results_pdf.html')
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.CreatePDF(BytesIO(html.encode("UTF-8")), dest=result)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="resume_analysis_{analysis_id}.pdf"'
        return response
    return HttpResponse("Error generating PDF", status=400)