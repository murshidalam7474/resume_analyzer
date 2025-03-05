import re
import nltk
import spacy
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pdfminer.high_level import extract_text
import docx

# Download necessary NLTK data
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

# Load spaCy medium model for improved semantic similarity
nlp = spacy.load('en_core_web_md')

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        text = extract_text(pdf_path)
        return text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""

def extract_text_from_docx(docx_path):
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(docx_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        print(f"Error extracting text from DOCX: {e}")
        return ""

def extract_contact_info(text):
    """Extract name, email, and phone number from resume text"""
    contact_info = {
        'name': None,
        'email': None,
        'phone': None
    }
    
    # Extract email
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    email_matches = re.findall(email_pattern, text)
    if email_matches:
        contact_info['email'] = email_matches[0]
    
    # Extract phone number - supports multiple formats
    phone_pattern = r'(\+\d{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\d{10}|\d{3}[-.\s]?\d{3}[-.\s]?\d{4})'
    phone_matches = re.findall(phone_pattern, text)
    if phone_matches:
        # Join the matched groups and clean up
        phone = ''.join(filter(None, phone_matches[0]))
        phone = re.sub(r'[^\d+]', '', phone)  # Keep only digits and + sign
        
        # Format the phone number
        if len(phone) >= 10:
            contact_info['phone'] = phone
    
    # Try to extract name using spaCy NER
    doc = nlp(text[:500])  # Limit to first 500 chars where name likely appears
    person_entities = [ent.text for ent in doc.ents if ent.label_ == 'PERSON']
    
    # If spaCy found person entities, use the first one as the name
    if person_entities:
        contact_info['name'] = person_entities[0]
    else:
        # Fallback: Try to find name at the beginning of the resume
        # Look for lines that don't contain common resume headers
        lines = text.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line and len(line) > 3 and not any(header in line.lower() for header in ['resume', 'cv', 'curriculum', 'email', 'phone', 'address', 'objective']):
                # If line has 2-3 words and no digits, it's likely a name
                words = line.split()
                if 1 <= len(words) <= 3 and not any(char.isdigit() for char in line):
                    contact_info['name'] = line
                    break
    
    return contact_info

def preprocess_text(text):
    """Clean and preprocess text"""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\d+', ' ', text)
    
    tokens = word_tokenize(text)
    stop_words = set(stopwords.words('english'))
    tokens = [token for token in tokens if token not in stop_words]
    
    lemmatizer = WordNetLemmatizer()
    tokens = [lemmatizer.lemmatize(token) for token in tokens]
    
    preprocessed_text = ' '.join(tokens)
    return preprocessed_text

def extract_skills(text):
    """Extract skills from text using a predefined skills database and spaCy NER"""
    skills_db = [
        'python', 'java', 'javascript', 'html', 'css', 'sql', 'nosql', 'mongodb',
        'react', 'angular', 'vue', 'node', 'express', 'django', 'flask', 'spring',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform', 'jenkins',
        'git', 'agile', 'scrum', 'kanban', 'jira', 'confluence', 'bitbucket',
        'machine learning', 'artificial intelligence', 'data science', 'nlp',
        'deep learning', 'computer vision', 'statistics', 'data analysis',
        'leadership', 'communication', 'teamwork', 'problem solving', 'critical thinking'
        
    ]
    
    text = text.lower()
    found_skills = []
    for skill in skills_db:
        if re.search(r'\b' + re.escape(skill) + r'\b', text):
            found_skills.append(skill)
    
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ['ORG', 'PRODUCT'] and ent.text.lower() not in found_skills:
            if len(ent.text) > 2 and not ent.text.isdigit():
                found_skills.append(ent.text.lower())
    
    return found_skills

def analyze_resume_job_match(resume_text, job_text):
    """Match resume to job description and provide detailed analysis"""
    # Extract contact information from resume
    contact_info = extract_contact_info(resume_text)
    
    preprocessed_resume = preprocess_text(resume_text)
    preprocessed_job = preprocess_text(job_text)
    
    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_text)
    
    matched_skills = [skill for skill in resume_skills if skill in job_skills]
    missing_skills = [skill for skill in job_skills if skill not in resume_skills]
    
    if len(job_skills) > 0:
        skill_match_percentage = (len(matched_skills) / len(job_skills)) * 100
    else:
        skill_match_percentage = 0
    
    # TF–IDF semantic similarity using bi-grams
    tfidf_vectorizer = TfidfVectorizer(ngram_range=(1,2), stop_words='english')
    tfidf_matrix = tfidf_vectorizer.fit_transform([preprocessed_resume, preprocessed_job])
    cosine_sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
    tfidf_sim_percentage = cosine_sim * 100

    # spaCy semantic similarity
    doc_resume = nlp(preprocessed_resume)
    doc_job = nlp(preprocessed_job)
    spacy_sim_percentage = doc_resume.similarity(doc_job) * 100

    # Combined semantic similarity (weighted equally here)
    semantic_match_percentage = (tfidf_sim_percentage + spacy_sim_percentage) / 2
    
    recommendations = []
    if missing_skills:
        recommendations.append(f"Consider adding these skills to your resume: {', '.join(missing_skills)}")
    if 'education' not in preprocessed_resume and 'education' in preprocessed_job:
        recommendations.append("The job posting emphasizes education credentials. Consider highlighting your education section.")
    if 'experience' not in preprocessed_resume and 'experience' in preprocessed_job:
        recommendations.append("The job posting emphasizes work experience. Make sure your experience section is well-detailed.")
    if 'certification' in preprocessed_job and 'certification' not in preprocessed_resume:
        recommendations.append("The job posting mentions certifications. Consider adding relevant certifications to your resume.")
    
    # Final match percentage: 60% skills, 40% semantic (you can tune these weights)
    final_match_percentage = (skill_match_percentage * 0.6) + (semantic_match_percentage * 0.4)
    
    result = {
        'match_percentage': round(final_match_percentage, 2),
        'skill_match_percentage': round(skill_match_percentage, 2),
        'semantic_match_percentage': round(semantic_match_percentage, 2),
        'matched_skills': matched_skills,
        'missing_skills': missing_skills,
        'recommendations': recommendations,
        'contact_info': contact_info  # Add contact info to the result
    }
    
    return result