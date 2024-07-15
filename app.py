from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def generate_email(professor_info):
    # A simple email generator function for testing
    return f"Hello Professor {professor_info['name']},\n\nI am interested in your work on {professor_info['research_interests']}.\n\nBest Regards,\n[Your Name]"

@app.route('/generate-email', methods=['POST'])
def generate_email_endpoint():
    data = request.json
    professor_info = {
        "name": data.get('name'),
        "university": data.get('university'),
        "research_interests": data.get('research_interests'),
    }
    email = generate_email(professor_info)
    return jsonify({"email": email})

if __name__ == '__main__':
    app.run(debug=True)
