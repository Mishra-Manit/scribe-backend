import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

cred_obj = firebase_admin.credentials.Certificate("coldemail-db-firebase-adminsdk-gn3cr-b1e821699b.json")
default_app = firebase_admin.initialize_app(cred_obj, {
	'databaseURL': "https://coldemail-db-default-rtdb.firebaseio.com/"
	})



"""
import json
with open("book_info.json", "r") as f:
	file_contents = json.load(f)
ref.set(file_contents)
"""

def send_email_to_firebase(professor_name, professor_interest, email_message):
    ref = db.reference(f"/requests/{professor_interest}_professor").push()
    ref.set({
        "professor_name": professor_name,
        "email_message": email_message
    })
    return "Email sent to Firebase"