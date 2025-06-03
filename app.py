from flask import Flask, request, jsonify
from flask_cors import CORS

import scholarpage

from googleapiclient.discovery import build
import requests
from bs4 import BeautifulSoup
import re
from openai import OpenAI

from firebase_func import send_email_to_firebase

app = Flask(__name__)
CORS(app)

print("Testing file started")


# Initialize OpenAI client
client = OpenAI(api_key='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')

# Initialize Google Custom Search API
def google_search(search_term, api_key, cse_id, **kwargs):
    service = build("customsearch", "v1", developerKey=api_key)
    res = service.cse().list(q=search_term, cx=cse_id, **kwargs).execute()
    return res['items']

# Scrape website text
def scrape_website_text(url):
    try:
        # Add headers to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        page = requests.get(url, headers=headers, timeout=10)
        
        # Try to detect encoding
        if page.encoding == 'ISO-8859-1' and 'charset' not in page.headers.get('content-type', ''):
            # Try to detect actual encoding
            page.encoding = page.apparent_encoding
        
        soup = BeautifulSoup(page.content, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Get text
        text = soup.get_text()
        
        # Clean up text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    except requests.exceptions.Timeout:
        print(f"Timeout error scraping {url}")
        return ""
    except requests.exceptions.RequestException as e:
        print(f"Request error scraping {url}: {e}")
        return ""
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
    
    # Try multiple search strategies for better results
    search_queries = [
        f"{professor_name} {professor_interest} publications research papers",
        f"{professor_name} site:edu publications",
        f"{professor_name} {professor_interest} general information"
    ]
    
    all_scraped_text = ""
    urls_scraped = set()  # Avoid duplicate URLs
    
    for search_term in search_queries[:2]:  # Use first 2 queries to avoid too much data
        print(f"Searching for {search_term}...")
        
        try:
            # Perform Google Custom Search
            results = google_search(search_term, api_key, cse_id, num=3)  # Increased back to 3 for better coverage
            
            for result in results:
                url = result['link']
                
                # Skip if already scraped
                if url in urls_scraped:
                    continue
                
                # Skip PDF files and other non-HTML content
                if url.endswith('.pdf') or url.endswith('.doc') or url.endswith('.docx'):
                    print(f"Skipping non-HTML URL: {url}")
                    continue
                    
                # Prioritize .edu domains and Google Scholar, but don't exclude others
                priority_site = '.edu' in url or 'scholar.google' in url or 'researchgate' in url or 'linkedin' in url
                
                if priority_site:
                    print(f"Scraping priority URL: {url}...")
                else:
                    print(f"Scraping URL: {url}...")
                
                try:
                    text = scrape_website_text(url)
                    if text and len(text.strip()) > 100:  # Only add if scraping succeeded and has meaningful content
                        all_scraped_text += f"URL: {url}\n\n{text}\n\n" + "#" * 100 + "\n\n"
                        urls_scraped.add(url)
                        print(f"Successfully scraped {len(text)} characters from {url}")
                    else:
                        print(f"Skipped {url} - insufficient content")
                except Exception as e:
                    print(f"Failed to scrape {url}: {e}")
                    continue
                
                # Stop if we have enough content
                if len(all_scraped_text) > 50000:  # Reasonable limit
                    break
                    
                # If not a priority site, limit to 2 non-priority sites
                if not priority_site and len([u for u in urls_scraped if '.edu' not in u and 'scholar.google' not in u]) >= 2:
                    break
                    
        except Exception as e:
            print(f"Error with search query '{search_term}': {e}")
            continue
            
        if len(all_scraped_text) > 50000:
            break
    
    # If we have very little content, be less restrictive and try the third query
    if len(all_scraped_text) < 1000 and len(search_queries) > 2:
        print(f"Insufficient content found. Trying additional search: {search_queries[2]}")
        try:
            results = google_search(search_queries[2], api_key, cse_id, num=3)
            for result in results[:3]:  # Limit to first 3
                url = result['link']
                if url not in urls_scraped and not url.endswith('.pdf'):
                    print(f"Scraping additional URL: {url}...")
                    try:
                        text = scrape_website_text(url)
                        if text and len(text.strip()) > 100:
                            all_scraped_text += f"URL: {url}\n\n{text}\n\n" + "#" * 100 + "\n\n"
                            urls_scraped.add(url)
                            print(f"Successfully scraped {len(text)} characters from {url}")
                    except Exception as e:
                        print(f"Failed to scrape {url}: {e}")
        except Exception as e:
            print(f"Error with fallback search: {e}")
    
    print(f"Total scraped content length: {len(all_scraped_text)} characters from {len(urls_scraped)} URLs")
    cleaned_content = cleanText(all_scraped_text)
    return cleaned_content

def summarize_chunk(chunk, professor_interest):
    system_msg = '''You are an expert academic information extractor. Your task is to analyze web content and extract structured information about professors with high accuracy and detail.'''
    
    user_msg = f'''
    Extract and organize ALL academic information about this {professor_interest} professor from the text below.
    
    OUTPUT FORMAT (use these exact headers):
    
    **PUBLICATIONS & RESEARCH:**
    - List each publication with its complete title in quotes
    - Include year and journal/conference if mentioned
    - Note citation counts if available
    
    **RESEARCH INTERESTS:**
    - List specific research areas and topics
    - Include current projects or focus areas
    
    **ACADEMIC BACKGROUND:**
    - Education history (degrees, institutions)
    - Academic positions held
    - Department affiliations
    
    **AWARDS & RECOGNITION:**
    - List any awards, honors, or distinctions
    - Include year received if mentioned
    
    **TEACHING:**
    - Courses taught
    - Teaching philosophy or approach if mentioned
    
    **COLLABORATIONS & IMPACT:**
    - Notable collaborations or joint work
    - Industry partnerships
    - Research impact or applications
    
    IMPORTANT INSTRUCTIONS:
    1. Include EXACT titles for all publications - this is critical
    2. If information for a section isn't found, write "Not found in source"
    3. Be comprehensive - don't summarize, extract everything relevant
    4. Maintain academic accuracy - only include what's explicitly stated
    
    SOURCE TEXT:
    {chunk}
    '''

    completion = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.1,  # Lower temperature for more consistent extraction
        max_tokens=32768,
        top_p=0.95,  # Slightly lower for more focused responses
        frequency_penalty=0,
        presence_penalty=0
    )
    return completion.choices[0].message.content


def summarize_text(scraped_content, professor_interest):
    CHUNK_SIZE = 900000
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

def validate_and_clean_email(email_content, professor_name):
    """Validate and clean the generated email to ensure quality"""
    
    # Check for common issues
    issues = []
    
    # Check for remaining brackets
    if '[' in email_content or ']' in email_content:
        issues.append("Unfilled brackets detected")
    
    # Check for placeholder text
    placeholder_patterns = [
        'NO_SCHOLARLY_DATA_AVAILABLE',
        'Not available',
        'not found in source',
        'PLACEHOLDER',
        '[INSERT]',
        'TODO'
    ]
    
    for pattern in placeholder_patterns:
        if pattern.lower() in email_content.lower():
            issues.append(f"Placeholder text '{pattern}' found")
    
    # Check if professor name is mentioned
    if professor_name.split()[-1] not in email_content:  # Check last name
        issues.append("Professor name not properly included")
    
    # Check for minimum length (too short emails are suspicious)
    if len(email_content.strip()) < 100:
        issues.append("Email appears too short")
    
    # Clean up formatting while preserving paragraph breaks
    # Split by double newlines to preserve paragraphs
    paragraphs = email_content.split('\n\n')
    cleaned_paragraphs = []
    
    for paragraph in paragraphs:
        # Clean up spaces within each paragraph
        cleaned_paragraph = re.sub(r'[ \t]+', ' ', paragraph)
        cleaned_paragraph = cleaned_paragraph.strip()
        if cleaned_paragraph:  # Only add non-empty paragraphs
            cleaned_paragraphs.append(cleaned_paragraph)
    
    # Rejoin paragraphs with double newlines
    email_content = '\n\n'.join(cleaned_paragraphs)
    
    return email_content, issues

def final_together(email_template, professor_name, professor_interest, user_id, source="generate"):
    email_messages = []

    print("Professor name: ", professor_name)
    print("[DEBUG] Starting scrape_professor_publications")
    scraped_content = scrape_professor_publications(professor_name, professor_interest)
    print("[DEBUG] Finished scrape_professor_publications, starting summarize_text")
    cleaned_content = summarize_text(scraped_content, professor_interest)
    print("[DEBUG] Finished summarize_text, starting scholarpage.search_for_author_exact_match")

    author_profile = scholarpage.search_for_author_exact_match(professor_name)
    print(f"[DEBUG] scholarpage.search_for_author_exact_match returned: {author_profile}")

    text_from_scholarly = " "

    #print("Author profile: ", author_profile)

    if author_profile:
        print("[DEBUG] Author profile found, calling scholarpage.get_top_cited_and_recent_papers")
        top_papers = scholarpage.get_top_cited_and_recent_papers(author_profile)
        print("[DEBUG] Finished scholarpage.get_top_cited_and_recent_papers")
        for title, citations, year in top_papers:
            text_from_scholarly += f"Title: {title}, Citations: {citations}, Year: {year}\n"
    else:
        text_from_scholarly = "NO_SCHOLARLY_DATA_AVAILABLE"
        print("[DEBUG] No author profile found, text_from_scholarly set to NO_SCHOLARLY_DATA_AVAILABLE")

    print("text from scholarly: ", text_from_scholarly)
    #This email HAS TO INCLUDE A PUBLICATION NAME IN THE EMAIL.

    system_msg2 = '''You are an expert cold email writer who specializes in crafting authentic, human-like academic outreach emails. Your PRIMARY goal is to write in a natural, conversational way that perfectly matches the sender's unique writing style and tone.

    WRITING PHILOSOPHY:
    - Write like a real person, not an AI - avoid robotic or overly formal language
    - Every email template has its own personality - study and mirror it exactly
    - The recipient should feel like they're hearing from a genuine human who took time to research them
    - Natural flow is more important than perfect grammar - write how people actually email

    CORE RESPONSIBILITIES:
    1. MATCH THE EXACT WRITING STYLE: Study the template's vocabulary, sentence structure, energy level, and personality
    2. Replace ALL text within square brackets [ ] with appropriate, specific information
    3. Preserve ALL other text in the template exactly as written
    4. Write replacements that sound like they came from the same person who wrote the template
    5. PRESERVE THE ORIGINAL FORMATTING - maintain paragraph breaks, line spacing, and structure

    STYLE MATCHING GUIDELINES:
    - If the template is casual and uses contractions, your replacements should too
    - If the template is energetic with exclamation points, maintain that energy
    - If the template is reserved and formal, keep replacements similarly professional
    - Match the sentence length patterns - short & punchy or long & flowing
    - Use similar vocabulary complexity as the surrounding text
    - Ensure replacements flow seamlessly with the template text'''



    user_msg2 = '''TASK: Fill in this cold email template for Professor {professor_name}, a {professor_interest} professor.

    STEP 1 - ANALYZE THE WRITING STYLE:
    Before making any replacements, carefully study the template to understand:
    - The overall tone (casual/formal, enthusiastic/reserved, etc.)
    - Typical sentence length and structure
    - Vocabulary choices and complexity
    - Use of punctuation and formatting
    - The writer's personality that comes through

    TEMPLATE TO COMPLETE:
    {email_template}

    AVAILABLE INFORMATION:

    === GOOGLE SCHOLAR DATA ===
    {text_from_scholarly}

    === WEB SEARCH DATA ===
    {cleaned_content}

    CRITICAL INSTRUCTIONS FOR NATURAL WRITING:
    1. Your replacements should sound EXACTLY like the person who wrote the template
    2. Prioritize natural flow over perfect accuracy - write how a real person would
    3. Use conversational transitions and connectors that match the template style
    4. If the template is informal, your replacements should be equally informal
    5. Avoid AI-sounding phrases like "cutting-edge", "groundbreaking", "innovative" unless the template uses similar language
    6. Include specific publication titles, but introduce them naturally as the template writer would
    7. PRESERVE ALL PARAGRAPH BREAKS AND FORMATTING from the original template

    WRITING STYLE EXAMPLES:
    
    If template says: "Hey! I was blown away by [publication]..."
    Good replacement: "Hey! I was blown away by your paper on neural networks in robotics..."
    Bad replacement: "Hey! I was blown away by your groundbreaking research publication titled 'Neural Networks in Robotics'..."

    If template says: "I found [specific aspect] particularly interesting..."
    Good replacement: "I found your approach to handling noisy sensor data particularly interesting..."
    Bad replacement: "I found the innovative methodology you employed particularly interesting..."

    REMEMBER:
    - Write like you're the same person who wrote the template
    - Keep the energy level consistent throughout
    - Make it feel genuine and personal, not like a mail merge
    - The professor should feel like they're getting a real, thoughtful email from someone who actually read their work

    Generate the complete email now, with all brackets filled naturally and authentically:'''.format(
            professor_name=professor_name, 
            professor_interest=professor_interest,
            email_template=email_template, 
            text_from_scholarly=text_from_scholarly, 
            cleaned_content=cleaned_content
    )

    print("[DEBUG] Starting final OpenAI API call for email generation")
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg2},
            {"role": "user", "content": user_msg2}
        ],
        temperature=0.7,  # Lower from 1.0 for more consistent output
        top_p=0.9,  # Add top_p for better quality
        frequency_penalty=0.1,  # Slight penalty to avoid repetition
        presence_penalty=0.1  # Slight penalty for more natural language
    )
    
    # Validate the generated email
    generated_email = completion.choices[0].message.content
    print("[DEBUG] Finished final OpenAI API call")
    cleaned_email, issues = validate_and_clean_email(generated_email, professor_name)
    
    # If there are critical issues, try to regenerate with more explicit instructions
    if issues and any('bracket' in issue or 'Placeholder' in issue for issue in issues):
        print(f"Issues detected in generated email: {issues}")
        print("Attempting to regenerate with stricter instructions...")
        
        # Add a more explicit prompt for the retry
        retry_msg = user_msg2 + f'''
        
        IMPORTANT: The previous attempt had these issues: {', '.join(issues)}

        Please ensure:
        - ALL brackets [ ] are replaced with actual content that sounds natural and human
        - NO placeholder text remains - write genuine, conversational replacements
        - Include specific publication titles but introduce them naturally
        - The email flows like it was written by one person, not assembled by AI
        - PRESERVE ALL PARAGRAPH BREAKS from the original template
        - Keep the exact same paragraph structure as the input template
        - Most importantly: Make it sound like the same person who wrote the template!

        Remember: Natural, human-like writing is MORE important than formal correctness.

        Generate the corrected email:'''
        
        print("[DEBUG] Starting OpenAI API call for email generation retry")
        retry_completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg2},
                {"role": "user", "content": retry_msg}
            ],
            temperature=0.5,  # Even lower temperature for retry
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.1
        )
        
        cleaned_email, issues = validate_and_clean_email(retry_completion.choices[0].message.content, professor_name)
        print("[DEBUG] Finished OpenAI API call for email generation retry")
        
        if issues:
            print(f"Warning: Email still has issues after retry: {issues}")
    
    email_messages.append({"Professor Name": professor_name, 
                            "Email Content": cleaned_email})
    print(cleaned_email)
    print("[DEBUG] Starting send_email_to_firebase")
    send_email_to_firebase(user_id, professor_name, professor_interest, cleaned_email, source)
    print("[DEBUG] Finished send_email_to_firebase")

    return email_messages

@app.route('/generate-email', methods=['POST'])
def generate_email_endpoint():
    print(" 2 Testing file started")
    data = request.get_json()
    print("Received data:", data)
    
    # Extract required fields
    email_template = data.get('email_template')
    professor_name = data.get('name')
    professor_interest = data.get('professor_interest')
    user_id = data.get('userId')
    source = data.get('source', 'generate')  # Default to 'generate' if not provided
    
    # Validate required fields
    if not all([email_template, professor_name, professor_interest, user_id]):
        return jsonify({"error": "Missing required fields"}), 400
    
    print(f"Professor name: {professor_name}, User ID: {user_id}, Source: {source}")

    email_message = final_together(email_template, professor_name, professor_interest, user_id, source)

    return jsonify(email_message)

if __name__ == '__main__':
    app.run(debug=True)