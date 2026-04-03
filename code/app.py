from flask import Flask, render_template, request, redirect, url_for, session
import subprocess
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Needed for session

# ✅ Added missing home route
@app.route('/')
def home():
    return redirect(url_for('code'))

questions = [
    {
        'id': 1,
        'title': "Sum of Two Numbers",
        'description': "Write a function called 'sum_numbers' that takes two numbers as arguments and returns their sum.",
        'test_cases': [
            {'input': 'sum_numbers(2, 3)', 'expected': '5'},
            {'input': 'sum_numbers(-1, 1)', 'expected': '0'},
            {'input': 'sum_numbers(0, 0)', 'expected': '0'}
        ]
    },
    {
        'id': 2,
        'title': "Factorial Calculation",
        'description': "Write a function called 'factorial' that takes a non-negative integer n and returns its factorial.",
        'test_cases': [
            {'input': 'factorial(0)', 'expected': '1'},
            {'input': 'factorial(1)', 'expected': '1'},
            {'input': 'factorial(5)', 'expected': '120'}
        ]
    },
    {
        'id': 3,
        'title': "Reverse String",
        'description': "Write a function called 'reverse_string' that takes a string as input and returns the reversed string.",
        'test_cases': [
            {'input': 'reverse_string("hello")', 'expected': "'olleh'"},
            {'input': 'reverse_string("")', 'expected': "''"},
            {'input': 'reverse_string("a")', 'expected': "'a'"}
        ]
    }
]

@app.route('/code')
def code():
    session.clear()  # Reset the session when starting fresh
    return render_template('code.html', total=len(questions))

@app.route('/coding_questions')
def start_code():
    session['current_question'] = 0  # Using 0-based index
    session['answers'] = []
    return redirect(url_for('show_question'))

@app.route('/question', methods=['GET', 'POST'])
def show_question():
    if 'current_question' not in session:
        return redirect(url_for('code'))
    
    current_idx = session['current_question']
    
    if request.method == 'POST':
        # Save the answer
        user_code = request.form['code']
        question_data = questions[current_idx]
        is_correct = evaluate_code(user_code, question_data['test_cases'])
        
        session['answers'].append({
            'question_id': question_data['id'],
            'code': user_code,
            'correct': is_correct
        })
        
        # Move to next question or show results
        if current_idx + 1 < len(questions):
            session['current_question'] += 1  # Increment the question index
            return redirect(url_for('show_question'))
        else:
            # All questions answered - show results
            session.pop('current_question', None)  # Remove 'current_question' from session
            return redirect(url_for('show_results'))
    
    # GET request - show current question
    question_data = questions[current_idx]
    progress = f"Question {current_idx + 1} of {len(questions)}"
    return render_template('question.html', 
                         question=question_data,
                         progress=progress,
                         questions=questions)

@app.route('/results')
def show_results():
    if 'answers' not in session or len(session['answers']) != len(questions):
        return redirect(url_for('code'))
    
    correct_count = sum(1 for answer in session['answers'] if answer['correct'])
    return render_template('code_result.html',
                         answers=session['answers'],
                         questions=questions,
                         correct_count=correct_count,
                         total=len(questions))

def evaluate_code(user_code, test_cases):
    temp_file = 'temp_user_code.py'
    with open(temp_file, 'w') as f:
        f.write(user_code)
    
    try:
        user_namespace = {}
        with open(temp_file) as f:
            exec(f.read(), user_namespace)
    except Exception:
        os.remove(temp_file)
        return False
    
    try:
        for case in test_cases:
            # Compile and evaluate expected output to handle string literals correctly
            expected = compile(case['expected'], '<string>', 'eval')
            received = eval(case['input'], user_namespace)
            if received != eval(expected):
                return False
    except Exception:
        return False
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return True

if __name__ == '__main__':
    app.run(debug=False)
