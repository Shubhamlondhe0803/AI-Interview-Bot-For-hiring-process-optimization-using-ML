from flask import Flask, render_template, request, redirect, url_for, flash, send_file,jsonify
from flask_sqlalchemy import SQLAlchemy
import csv
from difflib import SequenceMatcher
from fpdf import FPDF
import os
import cv2
import base64
import numpy as np
from coding_module import questions,evaluate_code
from flask import Flask, render_template, request, redirect, url_for, session
import subprocess
import os



# Load built-in Haar cascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Needed for flashing messages

# Configure SQLite Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///interview.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# Common Interview Questions
common_questions = [
    "What motivates you in your career?",
    "Can you describe a challenging project you've worked on?",
    "Where do you see yourself in 5 years?",
    "How do you handle criticism?",
    "Why should we hire you?"
]

# Load Technical Questions and Answers
def load_technical_questions(role):
    technical_questions = []
    answers = {}
    with open("technical_questions.csv", "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["role"] == role:
                technical_questions.append(row["question"])
                answers[row["question"]] = row["answer"]
    return technical_questions[:3], answers  # Limit to 3 technical questions

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Load a pre-trained model (You can try 'paraphrase-MiniLM-L6-v2' for speed or 'all-MiniLM-L6-v2')
model = SentenceTransformer('paraphrase-MiniLM-L6-v2')

def calculate_similarity(answer1, answer2):
    """Calculate semantic similarity between two answers."""
    embeddings = model.encode([answer1, answer2])
    similarity_score = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return similarity_score

# Candidate Table
class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    college = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=True)
    resume_filename = db.Column(db.String(200), nullable=True)  # <-- Add this line

# MCQ Test Results
class MCQResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)

# Verbal Answer Storage
class VerbalAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    marks = db.Column(db.Integer, nullable=True)

# New Table: Stores Generated Reports
class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate.id'), nullable=False)
    overall_score = db.Column(db.Integer, nullable=False)
    outcome = db.Column(db.String(50), nullable=False)  # "Recommended" or "Needs Improvement"
    mcq_score = db.Column(db.Integer, nullable=False)
    technical_score = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(50), nullable=True)

# Initialize DB Function
def init_db(app):
    with app.app_context():
        db.create_all()
        

# Load MCQs from CSV
def load_mcqs(role):
    mcqs = []
    with open("mcq_questions.csv", "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["role"] == role:
                mcqs.append({
                    "question": row["question"],
                    "options": [row["option1"], row["option2"], row["option3"], row["option4"]],
                    "answer": row["answer"]
                })
    return mcqs[:10]  # First 10 questions

@app.route('/')
def home():
    return render_template('start.html')  # Directly render start.html


# Start Interview -> Redirect to Select Role
@app.route('/start', methods=['GET', 'POST'])
def start():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        college = request.form['college']

        if 'resume' not in request.files:
            flash("Resume file is missing!", "danger")
            return redirect(url_for('start'))

        resume = request.files['resume']
        resume_filename = None

        if resume and resume.filename.endswith('.pdf'):
            resume_filename = f"{email}_resume.pdf"
            resume_path = os.path.join('static/resumes', resume_filename)
            os.makedirs(os.path.dirname(resume_path), exist_ok=True)
            resume.save(resume_path)

        candidate = Candidate.query.filter_by(email=email).first()
        if not candidate:
            candidate = Candidate(name=name, email=email, college=college, resume_filename=resume_filename)
            db.session.add(candidate)
            db.session.commit()

        return redirect(url_for('select_role', email=email))
    
    return render_template('start.html')

# Admin credentials (you can modify this later for database-based login)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Admin Login Route
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid Credentials!", "danger")

    return render_template('admin_login.html')


# Admin Dashboard - Show all candidates & scores
@app.route('/admin_dashboard')
def admin_dashboard():
    candidates = Candidate.query.all()  # Fetch all candidates

    # Fetch MCQ results
    mcq_results = {result.candidate_id: result for result in MCQResult.query.all()}

    # Fetch Verbal Results (Sum of Marks)
    verbal_results = {
        candidate.id: sum(ans.marks for ans in VerbalAnswer.query.filter_by(candidate_id=candidate.id) if ans.marks)
        for candidate in candidates
    }

    # Pass data to the template
    return render_template(
        'admin_dashboard.html',
        candidates=candidates,
        mcq_results=mcq_results,
        verbal_results=verbal_results,
        pdf_path=None  # Initially, no report
    )

@app.route('/verbal_report', methods=['GET', 'POST'])
def verbal_report():
    verbal_answers = []
    candidate = None  # Default

    if request.method == 'POST':
        candidate_id = request.form.get('candidate_id')

        if candidate_id:
            # Convert candidate_id to an integer
            try:
                candidate_id = int(candidate_id)

                # Fetch candidate details
                candidate = Candidate.query.filter_by(id=candidate_id).first()

                # Fetch verbal answers
                verbal_answers = VerbalAnswer.query.filter_by(candidate_id=candidate_id).all()

                if not verbal_answers:
                    flash("No verbal answers found for this Candidate ID.", "warning")
            except ValueError:
                flash("Invalid Candidate ID!", "danger")

    return render_template('verbal_report.html', verbal_answers=verbal_answers, candidate=candidate)

# Role Selection Page
@app.route('/select_role', methods=['GET', 'POST'])
def select_role():
    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email')

        if not email:
            return redirect(url_for('start'))

        candidate = Candidate.query.filter_by(email=email).first()
        if candidate:
            candidate.role = role
            db.session.commit()

        return redirect(url_for('mcq_test', role=role, email=email))
    
    email = request.args.get('email')
    return render_template('select_role.html', email=email)

# MCQ Test Page
@app.route('/mcq_test')
def mcq_test():
    role = request.args.get('role')
    email = request.args.get('email')

    if not role or not email:
        return redirect(url_for('select_role'))

    mcqs = load_mcqs(role)
    return render_template('mcq_test.html', mcqs=mcqs, role=role, email=email)

# Submit MCQ -> Show Result & Handle Passing Criteria
@app.route('/submit_mcq', methods=['POST'])
def submit_mcq():
    role = request.form.get('role')
    email = request.form.get('email')

    if not email:
        return redirect(url_for('start'))

    candidate = Candidate.query.filter_by(email=email).first()
    if not candidate:
        return redirect(url_for('start'))

    score = 0
    mcqs = load_mcqs(role)
    mcq_results = []  # To store each question, user's answer, and correct answer

    for i, mcq in enumerate(mcqs):
        user_answer = request.form.get(f"answer_{i}")
        correct_answer = mcq["answer"]
        is_correct = user_answer == correct_answer

        # Append the result for display
        mcq_results.append({
            "question": mcq["question"],
            "user_answer": user_answer if user_answer else "Not Answered",
            "correct_answer": correct_answer,
            "is_correct": is_correct
        })

        if is_correct:
            score += 1

    # Save MCQ results in the database
    mcq_result = MCQResult(candidate_id=candidate.id, score=score, total_questions=len(mcqs))
    db.session.add(mcq_result)
    db.session.commit()

    if score >= 6:
        flash("Congratulations! You passed the test. Click below to start the interview.", "success")
    else:
        flash("You are disqualified for this interview. Better luck next time!", "danger")

    return render_template('result.html', score=score, total=len(mcqs), email=email, mcq_results=mcq_results)

# Result Page
@app.route('/result')
def result():
    score = int(request.args.get('score', 0))
    total = int(request.args.get('total', 10))
    email = request.args.get('email')

    return render_template('result.html', score=score, total=total, email=email)

# Start Verbal Interview if Passed
@app.route('/verbal_interview')
def verbal_interview():
    email = request.args.get('email')
    candidate = Candidate.query.filter_by(email=email).first()
    
    if not candidate:
        return redirect(url_for('start'))
    
    role = candidate.role
    tech_questions, correct_answers = load_technical_questions(role)  # tech_questions is a tuple
    all_questions = list(tech_questions) + common_questions  # Convert tuple to list

    return render_template('index.html', question=all_questions[0], question_num=0, name=candidate.name, email=email, college=candidate.college, questions=all_questions)

# Store Verbal Answers and Move to Next Question
@app.route('/submit', methods=['POST'])
def submit():
    question_num = int(request.form['question_num'])
    answer = request.form['answer']
    email = request.form['email']
    
    candidate = Candidate.query.filter_by(email=email).first()
    if not candidate:
        return redirect(url_for('start'))
    
    role = candidate.role
    tech_questions, correct_answers = load_technical_questions(role)
    all_questions = tech_questions + ["What motivates you in your career?", "Where do you see yourself in 5 years?","Can you describe a challenging project you've worked on?",
    "How do you handle criticism?","Why should we hire you?"]  # Common questions
    
    marks = None
    if all_questions[question_num] in correct_answers:
        similarity = calculate_similarity(answer, correct_answers[all_questions[question_num]])
        marks = round(similarity * 10)  # Scale to 10 marks
    
    verbal_answer = VerbalAnswer(candidate_id=candidate.id, question=all_questions[question_num], answer=answer, marks=marks)
    db.session.add(verbal_answer)
    db.session.commit()
    
    if question_num + 1 < len(all_questions):
        return render_template('index.html', question=all_questions[question_num + 1], question_num=question_num + 1, email=email)
    else:
        return redirect(url_for('thank_you', email=email))

    # Save verbal answer to the database
    verbal_answer = VerbalAnswer(candidate_id=candidate.id, question=all_questions[question_num], answer=answer)
    db.session.add(verbal_answer)
    db.session.commit()

     # Move to next question or Thank You page
    if question_num + 1 < len(all_questions):
        next_question = all_questions[question_num + 1]
        return render_template('index.html', question=next_question, question_num=question_num + 1, name=name, email=email, college=college, questions=all_questions)
    else:
        return redirect(url_for('thank_you', email=email))

# PDF Generation Function
def generate_pdf(candidate, report_type="candidate"):
    mcq_result = MCQResult.query.filter_by(candidate_id=candidate.id).first()
    mcq_score = mcq_result.score if mcq_result else 0  # MCQ score is out of 10

    verbal_score = sum(ans.marks for ans in VerbalAnswer.query.filter_by(candidate_id=candidate.id) if ans.marks)  # Verbal score is out of 30
    total_score = mcq_score + verbal_score  # Overall Score (out of 40)
    outcome = "Recommended for Next Round" if total_score >= 17 else "Needs Improvement"

    technical_observation = "Strong grasp of technical skills." if mcq_score >= 6 else "Needs improvement in technical skills."
    problem_solving_observation = "Good problem-solving ability." if verbal_score >= 15 else "Struggles with complex problems."

    # Calculate additional statistics for Admin Report
    mcq_accuracy = round((mcq_score / 10) * 100, 2)  # MCQ accuracy percentage
    verbal_performance = round((verbal_score / 30) * 100, 2)  # Verbal performance percentage
    recommendation = "Candidate is suitable for the next round." if total_score >= 20 else "Candidate needs more improvement."

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", style='B', size=16)

    if report_type == "admin":
        pdf.cell(200, 10, txt="Admin Report - Candidate Performance", ln=True, align='C')
    else:
        pdf.cell(200, 10, txt="Your Interview Performance Report", ln=True, align='C')

    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Candidate: {candidate.name}", ln=True)
    pdf.cell(200, 10, txt=f"Position Applied: {candidate.role}", ln=True)
    pdf.cell(200, 10, txt=f"Email: {candidate.email}", ln=True)
    pdf.cell(200, 10, txt=f"College: {candidate.college}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 10, txt="Performance Overview:", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Overall Score: {total_score}/40", ln=True)
    pdf.cell(200, 10, txt=f"Interview Outcome: {outcome}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 10, txt="Key Metrics:", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Technical Competency (MCQ Score): {mcq_score}/10", ln=True)
    pdf.cell(200, 10, txt=f"Observation: {technical_observation}", ln=True)
    pdf.ln(3)
    pdf.cell(200, 10, txt=f"Problem-Solving Ability (Technical Score): {verbal_score}/30", ln=True)
    pdf.cell(200, 10, txt=f"Observation: {problem_solving_observation}", ln=True)
    pdf.ln(5)

    # 📌 Include Additional Notes ONLY in the Admin Report
    if report_type == "admin":
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(200, 10, txt="Additional Notes:", ln=True)
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"- MCQ Accuracy Rate: {mcq_accuracy}%", ln=True)
        pdf.cell(200, 10, txt=f"- Verbal Performance in Technical Questions: {verbal_performance}%", ln=True)
        pdf.cell(200, 10, txt=f"- Recommendation: {recommendation}", ln=True)
        pdf.ln(5)

    # Different filenames for Candidate & Admin Reports
    filename = f"static/reports/admin_candidate_{candidate.id}_report.pdf" if report_type == "admin" else f"static/reports/candidate_{candidate.id}_report.pdf"

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    pdf.output(filename)

    return filename

# Route to Generate PDF and Show on Dashboard
@app.route('/generate_report', methods=['POST'])
def generate_report():
    candidate_id = request.form.get('candidate_id')
    candidate = Candidate.query.filter_by(id=candidate_id).first()
    
    if not candidate:
        flash("Candidate not found!", "danger")
        return redirect(url_for('admin_dashboard'))

    # Generate Admin Report
    admin_pdf = generate_pdf(candidate, report_type="admin")

    candidates = Candidate.query.all()
    mcq_results = {result.candidate_id: result for result in MCQResult.query.all()}
    verbal_results = {
        candidate.id: sum(ans.marks for ans in VerbalAnswer.query.filter_by(candidate_id=candidate.id) if ans.marks)
        for candidate in candidates
    }

    return render_template(
        'admin_dashboard.html',
        candidates=candidates,
        mcq_results=mcq_results,
        verbal_results=verbal_results,
        pdf_path=admin_pdf  # Pass the admin report
    )


# 📌 Thank You Page Route
@app.route('/thank_you')
def thank_you():
    email = request.args.get('email')
    candidate = Candidate.query.filter_by(email=email).first()
    
    if not candidate:
        return redirect(url_for('start'))

    # Check if interview was terminated
    termination_record = VerbalAnswer.query.filter_by(
        candidate_id=candidate.id,
        question="Interview Termination"
    ).first()

    if termination_record:
        return render_template('thank_you.html', email=email, termination=True)

    total_score = sum(ans.marks for ans in VerbalAnswer.query.filter_by(candidate_id=candidate.id) if ans.marks)
    candidate_pdf = generate_pdf(candidate, report_type="candidate")

    return render_template('thank_you.html', email=email, score=total_score, pdf_path=candidate_pdf)

import cv2
import base64
import numpy as np
from flask import jsonify

# Load built-in Haar cascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
if face_cascade.empty():
    print("Error loading Haar cascade!")

@app.route('/detect_faces', methods=['POST'])
def detect_faces():
    data = request.get_json()
    image_data = data['image'].split(",")[1]
    img_bytes = base64.b64decode(image_data)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    print(f"Faces detected: {len(faces)}")  # 👈 Add this for debugging

    if len(faces) == 0:
        return jsonify({"label": "no_face"})
    elif len(faces) > 1:
        return jsonify({"label": "multiple_faces"})
    else:
        return jsonify({"label": "single_face"})

@app.route('/terminate_interview', methods=['POST'])
def terminate_interview():
    data = request.get_json()
    email = data.get('email')
    reason = data.get('reason', 'excessive_warnings')
    
    candidate = Candidate.query.filter_by(email=email).first()
    if candidate:
        # Create a special verbal answer record to mark termination
        termination_record = VerbalAnswer(
            candidate_id=candidate.id,
            question="Interview Termination",
            answer=f"Interview terminated due to: {reason}",
            marks=0
        )
        db.session.add(termination_record)
        db.session.commit()
    
    return jsonify({"status": "success"})

# In app.py - Update these routes

@app.route('/code')
def code():
    email = request.args.get("email")
    if not email:
        return redirect(url_for('start'))
    session['email'] = email  # Store email in session
    return render_template('code.html', total=len(questions), email=email)

@app.route('/coding_questions')
def start_code():
    email = request.args.get('email')
    if not email:
        if 'email' in session:
            email = session['email']
        else:
            return redirect(url_for('start'))
    
    session['current_question'] = 0
    session['answers'] = []
    session['email'] = email
    return redirect(url_for('show_question'))

@app.route('/question', methods=['GET', 'POST'])
def show_question():
    if 'current_question' not in session or 'email' not in session:
        return redirect(url_for('code', email=session.get('email')))
    
    current_idx = session['current_question']
    
    if request.method == 'POST':
        user_code = request.form['code']
        question_data = questions[current_idx]
        is_correct = evaluate_code(user_code, question_data['test_cases'])
        
        if 'answers' not in session:
            session['answers'] = []
        
        session['answers'].append({
            'question_id': question_data['id'],
            'code': user_code,
            'correct': is_correct
        })
        
        session.modified = True  # Ensure session is saved
        
        if current_idx + 1 < len(questions):
            session['current_question'] += 1
            return redirect(url_for('show_question'))
        else:
            # All questions answered - redirect to results
            return redirect(url_for('show_results'))
    
    question_data = questions[current_idx]
    progress = f"Question {current_idx + 1} of {len(questions)}"
    return render_template('question.html', 
                        question=question_data,
                        progress=progress,
                        questions=questions,
                        email=session.get('email'))

@app.route('/results')
def show_results():
    if 'answers' not in session or len(session['answers']) != len(questions) or 'email' not in session:
        return redirect(url_for('code', email=session.get('email')))
    
    answers = session['answers']
    correct_count = sum(1 for answer in answers if answer['correct'])
    email = session['email']
    
    # Clear session data
    session.pop('current_question', None)
    session.pop('answers', None)
    session.modified = True
    
    return render_template('code_result.html',
                         answers=answers,
                         questions=questions,
                         correct_count=correct_count,
                         total=len(questions),
                         email=email)


if __name__ == '__main__':
    app.run(debug=False)
