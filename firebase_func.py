import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

cred_obj = firebase_admin.credentials.Certificate("coldemail-db-firebase-adminsdk-gn3cr-b1e821699b.json")
default_app = firebase_admin.initialize_app(cred_obj, {
    'databaseURL': "https://coldemail-db-default-rtdb.firebaseio.com/"
})

def get_next_request_number():
    ref = db.reference("/requests")
    requests = ref.get()
    if not requests:
        return 1
    else:
        last_request_number = max([int(key.split('_')[1]) for key in requests.keys() if key.startswith('Request_')])
        return last_request_number + 1

def send_email_to_firebase(professor_name, professor_interest, email_message):
    next_request_number = get_next_request_number()
    request_key = f"Request_{next_request_number}"
    ref = db.reference(f"/requests/{request_key}")
    ref.set({
        "professor_name": professor_name,
        "professor_interest": professor_interest,
        "email_message": email_message
    })
    return "Email sent to Firebase"