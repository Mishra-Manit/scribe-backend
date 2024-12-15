import os
import base64
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText

# Scopes for Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.compose']

def authenticate_gmail():
    """Authenticate the user and return the Gmail service."""
    creds = None
    # Token file stores user credentials
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no valid credentials, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for future use
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def create_message(sender, to, subject, body_text):
    """Create a MIME email message."""
    message = MIMEText(body_text)
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw_message}

def create_draft(service, user_id, message_body):
    """Create a draft email."""
    try:
        draft = service.users().drafts().create(userId=user_id, body={'message': message_body}).execute()
        print(f"Draft created: {draft['id']}")
        return draft
    except Exception as error:
        print(f"An error occurred: {error}")
        return None

def main():
    # Authenticate and get the Gmail API service
    service = authenticate_gmail()
    
    # Email details
    sender = "manitsuperhero@gmail.com"
    to = "mshmanit@gmail.com"
    subject = "Draft Subject"
    body_text = "This is the body of the draft email."
    
    # Create message and draft
    message = create_message(sender, to, subject, body_text)
    create_draft(service, 'me', message)

if __name__ == '__main__':
    main()