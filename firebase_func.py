import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from datetime import datetime

cred_obj = firebase_admin.credentials.Certificate("coldauth-a5caf-firebase-adminsdk-fbsvc-274ef406d7.json")
default_app = firebase_admin.initialize_app(cred_obj)

# Initialize Firestore client
db = firestore.client()

def send_email_to_firebase(user_id, professor_name, professor_interest, email_message, source="generate"):
    """
    Save generated email to Firestore under user's emails collection
    
    Args:
        user_id: The ID of the user making the request
        professor_name: Name of the professor
        professor_interest: Interest/field of the professor
        email_message: Generated email content
        source: Origin of the request (default: "generate")
    """
    try:
        # Reference to the user's emails subcollection
        user_emails_ref = db.collection('users').document(user_id).collection('emails')
        
        # Create email document with timestamp
        email_doc = {
            'professor_name': professor_name,
            'professor_interest': professor_interest,
            'email_message': email_message,
            'source': source,
            'created_at': firestore.SERVER_TIMESTAMP,
            'status': 'generated'  # Can be used to track email status
        }
        
        # Add the document with auto-generated ID
        user_emails_ref.add(email_doc)
        
        print(f"Email for {professor_name} saved to Firestore for user {user_id}")
        return "Email sent to Firebase"
        
    except Exception as e:
        print(f"Error saving email to Firebase: {e}")
        raise e