from flask import Flask, request, jsonify
from flask_cors import CORS

import scholarpage

from googleapiclient.discovery import build
import requests
from bs4 import BeautifulSoup
import re
import openai

from firebase_func import send_email_to_firebase

app = Flask(__name__)
CORS(app)


openai.api_key = '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'
# Initialize Google Custom Search API
def google_search(search_term, api_key, cse_id, **kwargs):
    service = build("customsearch", "v1", developerKey=api_key)
    res = service.cse().list(q=search_term, cx=cse_id, **kwargs).execute()
    return res['items']

# Scrape website text
def scrape_website_text(url):
    try:
        page = requests.get(url)
        soup = BeautifulSoup(page.content, "html.parser")
        return soup.get_text()
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return ""

def is_english(text):
    return bool(re.search(r'[a-zA-Z]', text)) and text.count(' ') > 3

def cleanText(text):
    lines = text.splitlines()
    cleaned_lines = [line for line in lines if is_english(line)]
    cleaned_text = '\n'.join(cleaned_lines)
    cleaned_text = re.sub(r'[^\w\s.,;:()\'\"-]', '', cleaned_text)
    cleaned_text= re.sub(r'[^\x00-\x7F]+', '', cleaned_text)
    return cleaned_text

def scrape_professor_publications(professor_name, professor_interest):
    api_key = "AIzaSyD1J5WBjeWOeNTdAT5y5Cw8gztUriPRiuc"
    cse_id = "96fd38a2a138e4738"
    search_term = f"{professor_name} {professor_interest} information"

    print(f"Searching for {search_term}...")

    # Perform Google Custom Search
    results = google_search(search_term, api_key, cse_id, num=2)

    all_scraped_text = ""

    for result in results:
        url = result['link']
        print(f"Scraping {url}...")
        text = scrape_website_text(url)
        all_scraped_text += f"URL: {url}\n\n{text}\n\n" + "#" * 100 + "\n\n"
    cleaned_content = cleanText(all_scraped_text)
    return cleaned_content

def summarize_chunk(chunk, professor_interest):
    system_msg = 'You are an assistant summarizer. Extract the key information out of the text block provided to you.'
    user_msg = f'''
    I need anything academic related that this professor has received or teaches. Make sure to capture exact names of books and publications as well as the years they came out. Gather all of that information and put in a summarized format. Make sure to keep whole titles for everything. Write a good and concise summary about the professor through the below text provided.
    
    This email is for a {professor_interest} professor.

    You do not need to access the internet for this information. It is all in the text block I am pasting below.
    Retrieve all of that information from this text: {chunk}
    '''

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


def summarize_text(scraped_content, professor_interest):

    CHUNK_SIZE = 500000
    summarized_text = ""
    chunks = [scraped_content[i:i+CHUNK_SIZE] for i in range(0, len(scraped_content), CHUNK_SIZE)]

    for chunk in chunks:
        try:
            summarized_chunk = summarize_chunk(chunk, professor_interest)
            summarized_text += summarized_chunk + "\n"
        except Exception as e:
           print(f"Error summarizing text chunk: {e}")

    print("Here is the entire summarized text: ", summarized_text.strip())
    return summarized_text.strip() 


def replace_unsupported_characters(text):
    return text.encode('utf-8', errors='replace').decode('utf-8', errors='ignore')

def final_together(email_template, professor_name, professor_interest):
    email_messages = []

    print("Professor name: ", professor_name)
    scraped_content = scrape_professor_publications(professor_name, professor_interest)
    cleaned_content = summarize_text(scraped_content, professor_interest)

    author_profile = scholarpage.search_for_author_exact_match(professor_name)

    text_from_scholarly = " "

    if author_profile:
        top_cited_papers = scholarpage.get_top_cited_papers(author_profile)
        for title, citations in top_cited_papers:
            text_from_scholarly += f"Title: {title}, Citations: {citations}\n"

    else:
        text_from_scholarly = "Not available, replace this with information from google scrape"
    #text from scholarly: ", text_from_scholarly)
    #This email HAS TO INCLUDE A PUBLICATION NAME IN THE EMAIL.

    system_msg2 = 'You are an assistant that will use information provided to you to complete a cold email template. Keep all of the same email language, tone, or style. If the text provided is -Not available, replace this with information from google scrape.- DO NOT include the details about the professors paper. Skip that sentence and reference something else.'
    user_msg2 = '''
    This is the cold email template you need to fill out for Professor {}: {}

    Do not change the original template text, dont add extra paragraphs. DO NOT put extra text than the template provided. Do not give a subject line for the email.

    This email is for a {} professor. 

    Keep the email sounding the same as my writing and make it sound like it was written by me. Do not call this email an application. This email should be ready to be sent to the professor, so make sure to keep it that way. Do not make your own version for the ending of the message.

    ONLY alter the areas of the template that are in brackets. Do not change the rest of the email template text, just put the information that needs to be added. Make sure to actually add publication titles whereever applicable.

    After generating the email, double check that the voice of the email matches my writing and if it doesnt, rewrite the email. Also double check that all the information mentioned can be backed up with evidence as I am sending these emails directly to professors. Make it sound like a human (tone: conversational, 50 percent spartan) and rewrite.

    If the text provided is -Not available, replace this with information from google scrape.- do not write that sentence in the final email. Delete the sentence. If the text provided is -Not available, replace this with information from google scrape.- DO NOT include the details about the professors paper. Skip that sentence and reference something else.

    Papers: {}

    More information about the professor:
    {}
    '''.format(professor_name, email_template, professor_interest, text_from_scholarly, cleaned_content)

    completion = openai.ChatCompletion.create(
        model="gpt-4o-2024-05-13",
        messages=[
            {"role": "system", "content": system_msg2},
            {"role": "user", "content": user_msg2}
        ],
        temperature=1
    )
    
    email_messages.append({"Professor Name": professor_name, 
                            #"Subject Line": subject_line.choices[0].message['content'],
                            "Email Content": completion.choices[0].message['content']})
    print(completion.choices[0].message['content'])
    send_email_to_firebase(professor_name, professor_interest, completion.choices[0].message['content'])

    return email_messages

@app.route('/generate-email', methods=['POST'])
def generate_email_endpoint():
    data = request.get_json()
    print("Received data:", data)
    professor_info = {
        "email_template": data.get('email_template'),
        "name": data.get('name'),  # Expecting one professor name per request
        "professor_interest": data.get('professor_interest'),
    }
    print("Professor info name:", professor_info['name'])

    email_message = final_together(professor_info['email_template'], professor_info['name'], professor_info['professor_interest'])

    return jsonify(email_message)

if __name__ == '__main__':
    app.run(debug=True)