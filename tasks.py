from openai import OpenAI
from firebase_func import send_email_to_firebase
import scholarpage
from googleapiclient.discovery import build
import requests
from bs4 import BeautifulSoup
import re

# Initialize OpenAI client
client = OpenAI(api_key='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')

def google_search(search_term, api_key, cse_id, **kwargs):
    service = build("customsearch", "v1", developerKey=api_key)
    res = service.cse().list(q=search_term, cx=cse_id, **kwargs).execute()
    return res['items']

def scrape_website_text(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        page = requests.get(url, headers=headers, timeout=10)
        if page.encoding == 'ISO-8859-1' and 'charset' not in page.headers.get('content-type', ''):
            page.encoding = page.apparent_encoding
        soup = BeautifulSoup(page.content, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        return text
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
    search_queries = [
        f"{professor_name} {professor_interest} publications research papers",
        f"{professor_name} site:edu publications",
        f"{professor_name} {professor_interest} general information"
    ]
    all_scraped_text = ""
    urls_scraped = set()
    
    for search_term in search_queries[:2]:
        print(f"Searching for {search_term}...")
        try:
            results = google_search(search_term, api_key, cse_id, num=3)
            for result in results:
                url = result['link']
                if url in urls_scraped:
                    continue
                if url.endswith('.pdf') or url.endswith('.doc') or url.endswith('.docx'):
                    continue
                priority_site = '.edu' in url or 'scholar.google' in url or 'researchgate' in url or 'linkedin' in url
                try:
                    text = scrape_website_text(url)
                    if text and len(text.strip()) > 100:
                        all_scraped_text += f"URL: {url}\n\n{text}\n\n" + "#" * 100 + "\n\n"
                        urls_scraped.add(url)
                except Exception as e:
                    continue
                if len(all_scraped_text) > 50000:
                    break
                if not priority_site and len([u for u in urls_scraped if '.edu' not in u and 'scholar.google' not in u]) >= 2:
                    break
        except Exception as e:
            continue
        if len(all_scraped_text) > 50000:
            break
    
    if len(all_scraped_text) < 1000 and len(search_queries) > 2:
        try:
            results = google_search(search_queries[2], api_key, cse_id, num=3)
            for result in results[:3]:
                url = result['link']
                if url not in urls_scraped and not url.endswith('.pdf'):
                    try:
                        text = scrape_website_text(url)
                        if text and len(text.strip()) > 100:
                            all_scraped_text += f"URL: {url}\n\n{text}\n\n" + "#" * 100 + "\n\n"
                            urls_scraped.add(url)
                    except Exception as e:
                        continue
        except Exception as e:
            pass
    
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
        temperature=0.1,
        max_tokens=32768,
        top_p=0.95,
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

    return summarized_text.strip()

def validate_and_clean_email(email_content, professor_name):
    issues = []
    if '[' in email_content or ']' in email_content:
        issues.append("Unfilled brackets detected")
    
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
    
    if professor_name.split()[-1] not in email_content:
        issues.append("Professor name not properly included")
    
    if len(email_content.strip()) < 100:
        issues.append("Email appears too short")
    
    paragraphs = email_content.split('\n\n')
    cleaned_paragraphs = []
    
    for paragraph in paragraphs:
        cleaned_paragraph = re.sub(r'[ \t]+', ' ', paragraph)
        cleaned_paragraph = cleaned_paragraph.strip()
        if cleaned_paragraph:
            cleaned_paragraphs.append(cleaned_paragraph)
    
    email_content = '\n\n'.join(cleaned_paragraphs)
    
    return email_content, issues

def generate_email(email_template, professor_name, professor_interest, user_id, source="generate"):
    """Main task function for generating emails"""
    print("Professor name: ", professor_name)
    scraped_content = scrape_professor_publications(professor_name, professor_interest)
    cleaned_content = summarize_text(scraped_content, professor_interest)

    author_profile = scholarpage.search_for_author_exact_match(professor_name)
    text_from_scholarly = " "

    if author_profile:
        top_papers = scholarpage.get_top_cited_and_recent_papers(author_profile)
        for title, citations, year in top_papers:
            text_from_scholarly += f"Title: {title}, Citations: {citations}, Year: {year}\n"
    else:
        text_from_scholarly = "NO_SCHOLARLY_DATA_AVAILABLE"

    system_msg2 = '''You are an expert cold email writer who specializes in crafting authentic, human-like academic outreach emails...'''

    user_msg2 = f'''TASK: Fill in this cold email template for Professor {professor_name}, a {professor_interest} professor...'''

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg2},
            {"role": "user", "content": user_msg2}
        ],
        temperature=0.7,
        top_p=0.9,
        frequency_penalty=0.1,
        presence_penalty=0.1
    )
    
    generated_email = completion.choices[0].message.content
    cleaned_email, issues = validate_and_clean_email(generated_email, professor_name)
    
    if issues and any('bracket' in issue or 'Placeholder' in issue for issue in issues):
        print(f"Issues detected in generated email: {issues}")
        print("Attempting to regenerate with stricter instructions...")
        
        retry_msg = user_msg2 + f'''
        IMPORTANT: The previous attempt had these issues: {', '.join(issues)}...'''
        
        retry_completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg2},
                {"role": "user", "content": retry_msg}
            ],
            temperature=0.5,
            top_p=0.9,
            frequency_penalty=0.1,
            presence_penalty=0.1
        )
        
        cleaned_email, issues = validate_and_clean_email(retry_completion.choices[0].message.content, professor_name)
        
        if issues:
            print(f"Warning: Email still has issues after retry: {issues}")
    
    email_messages = [{"Professor Name": professor_name, "Email Content": cleaned_email}]
    send_email_to_firebase(user_id, professor_name, professor_interest, cleaned_email, source)

    return email_messages 