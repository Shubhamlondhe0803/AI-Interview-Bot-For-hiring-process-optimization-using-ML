import subprocess
import os


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
