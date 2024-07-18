from flask import Flask, request, jsonify
from flask_cors import CORS

from googleapiclient.discovery import build
import requests
from bs4 import BeautifulSoup
import re
import openai

app = Flask(__name__)
CORS(app)


openai.api_key = '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'

def openai_response(prompt):
    system_msg = 'You are an assistant. Answer the questions that are asked.'
    user_msg = prompt

    completion = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.5,
        max_tokens=2048,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    return completion.choices[0].message['content']

def generate_email(professor_info):
    return openai_response(professor_info['prompt'])

@app.route('/generate-email', methods=['POST'])
def generate_email_endpoint():
    data = request.get_json()  # Use request.get_json() to parse the JSON data
    print("Received data:", data)  # Debugging line to print received data
    professor_info = {
        "name": data.get('name'),
        "prompt": data.get('prompt'),
        "research_interests": data.get('research_interests'),
    }
    print("Professor info:", professor_info)  # Debugging line to print professor info
    email = generate_email(professor_info)
    return email

if __name__ == '__main__':
    app.run(debug=True)
