import csv
import datetime
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
import json
import threading
import time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Open the CSV file
campers_csv_path = './campers.csv'
logins_csv_path = './logins.csv'
UUIDs = []
first_names = []
last_names = []
middle_names = []
mother_IDs = []
father_IDs = []
DEBUG = True
# Google Sheets setup
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_sheets_service():
    """Get authenticated Google Sheets service"""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)

def get_config():
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        print("config.json not found. Using default values.")
        return {
            'SPREADSHEET_ID': '1XxALSucHzMbO1D7SQT-K037ue_zheiUPan4Oq6waOr0',
            'LEDGER_SHEET_NAME': 'Ledger'
        }

def get_data_from_csv_campers():
    global UUIDs, first_names, last_names, middle_names, mother_IDs, father_IDs
    try:
        with open(campers_csv_path, mode='r', newline='', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                data = [row for row in csv_reader]
            UUIDs = [row[0] for row in data]
            first_names = [row[1] for row in data]
            last_names = [row[2] for row in data]
            middle_names = [row[3] for row in data]
            mother_IDs = [row[10] for row in data]
            father_IDs = [row[11] for row in data]
                
    except FileNotFoundError:
        print(f"The file {campers_csv_path} does not exist.")

def generate_qr(camper_ID):
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=20,
        border=6,
    )
    qr.add_data(camper_ID)
    qr.make(fit=True)

    # Create an image from the QR Code instance
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save the image
    img.save(f"static/QRs/{camper_ID}.png")

def generate_QRs(debug=False):
    get_data_from_csv_campers()
    for i in range(len(UUIDs)):
        camper_ID = UUIDs[i]
        generate_qr(camper_ID)
        if debug:
            print(f"QR code for {camper_ID} generated.")
    print("All QR codes generated successfully.")

def get_name_from_ID(camper_ID):
    get_data_from_csv_campers()
    if camper_ID in UUIDs:
        index = UUIDs.index(camper_ID)
        first_name = first_names[index]
        last_name = last_names[index]
        return first_name + " " + last_name
    else:
        print(f"Camper ID {camper_ID} not found.")
        return None

def get_parent_name_from_camper_ID(camper_ID):
    """Get parent name for a given camper ID"""
    get_data_from_csv_campers()
    if camper_ID in UUIDs:
        index = UUIDs.index(camper_ID)
        # Try to get parent name from either mother or father ID
        mother_id = mother_IDs[index] if mother_IDs[index] != "" else None
        father_id = father_IDs[index] if father_IDs[index] != "" else None
        data = 0
        with open("parents.csv", mode='r', newline='', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                data = [row for row in csv_reader]
        pn = 'N/A'
        print(f"{mother_id}, {father_id}")
        for row in data:
            print(row)
            if row[0] == father_id or row[0] == mother_id:
                pn = row[3]
        return pn
    return None

def is_camper_logged_in(camper_ID):
    """Check if camper is currently logged in by checking the last entry"""
    try:
        with open(logins_csv_path, mode='r', newline='', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            rows = list(csv_reader)
            
            # Find the most recent entry for this camper
            for row in reversed(rows):
                if len(row) >= 3 and row[0] == camper_ID:
                    return row[2] == "login"
            
            # If no entry found, camper is not logged in
            return False
    except FileNotFoundError:
        return False

def login_user(camper_ID):
    """Handle login/logout for a user"""
    currently_logged_in = is_camper_logged_in(camper_ID)
    action = "logout" if currently_logged_in else "login"
    
    # Log to CSV
    with open(logins_csv_path, mode='a', newline='', encoding='utf-8') as file:
        time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        csv_writer = csv.writer(file)
        csv_writer.writerow([camper_ID, time, action])
        print(f"User {camper_ID} {action} at {time}.")
    
    # Update Google Sheet
    if(not DEBUG):
        threading.Thread(target=update_google_sheet_ledger, args=(camper_ID, time, action)).start()
    
    return action

def update_google_sheet_ledger(camper_ID, timestamp, action):
    """Update the Google Sheet ledger with login/logout information"""
    try:
        service = get_sheets_service()
        config = get_config()
        spreadsheet_id = config.get('LEDGER_SHEET_ID')
        sheet_name = config.get('LEDGER_SHEET_NAME', 'Ledger')
        
        # Get camper and parent names
        camper_name = get_name_from_ID(camper_ID)
        if not camper_name:
            print(f"Could not find name for camper ID: {camper_ID}")
            return
        
        # Format camper name as "Last, First"
        name_parts = camper_name.split(' ')
        if len(name_parts) >= 2:
            formatted_name = f"{name_parts[-1]}, {' '.join(name_parts[:-1])}"
        else:
            formatted_name = camper_name
        
        parent_name = get_parent_name_from_camper_ID(camper_ID)
        
        # Read current sheet data
        range_name = f"{sheet_name}!A:Z"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        
        if len(values) < 2:
            print("Sheet doesn't have proper header structure")
            return
        
        # Find or create row for this camper
        camper_row = None
        row_index = None
        formatted_name = formatted_name.rstrip()
        for i, row in enumerate(values[2:], start=3):  # Start from row 3 (index 2)
            if len(row) >= 3 and row[2] == formatted_name:
                camper_row = row
                row_index = i
                break
        
        # If camper not found, create new row
        if camper_row is None:
            row_index = len(values) + 1
            # Create new row: N, ParentName, ChildName, followed by empty columns
            next_n = len(values) - 1  # Subtract 2 for headers, add 1 for next number
            camper_row = [str(next_n), parent_name or "Unknown Parent", formatted_name] + [""] * 10
        
        # Determine which column to update based on day and action
        today = datetime.datetime.now()
        day_of_week = today.weekday()  # 0=Monday, 1=Tuesday, etc.
        time_only = timestamp.split(' ')[1][:5]  # Get HH:MM format
        
        # Column mapping: Mon In=3, Mon Out=4, Tue In=5, Tue Out=6, etc.
        day_names = ['Mon', 'Tue', 'Wed', 'Thur', 'Fri']

        if day_of_week < 5:  # Monday to Friday
            base_col = 3 + (day_of_week * 2)  # Starting column for the day
            col_index = base_col if action == "login" else base_col + 1
            
            # Ensure row has enough columns
            while len(camper_row) <= col_index:
                camper_row.append("")
            
            camper_row[col_index] = time_only
            
            # Update the sheet
            range_to_update = f"{sheet_name}!A{row_index}:M{row_index}"
            body = {'values': [camper_row]}
            
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_to_update,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            action_type = "In" if action == "login" else "Out"
            print(f"Updated Google Sheet: {formatted_name} - {day_names[day_of_week]} {action_type}: {time_only}")
        else:
            print("Weekend - not updating ledger sheet")
            
    except HttpError as error:
        print(f"An error occurred updating Google Sheet: {error}")
    except Exception as error:
        print(f"Unexpected error updating Google Sheet: {error}")

def get_full_names():
    get_data_from_csv_campers()
    full_names = [[f"{first} {middle} {last}",uuid] for first, middle, last, uuid in zip(first_names, middle_names, last_names, UUIDs)]
    return full_names

def add_name_to_image(image_path, name, debug=False):
    try:
        image = Image.open(image_path)
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("font.ttf", 50)
        
        draw.text((30, 20), name, font=font, fill=0)
        image.save(image_path)
        if debug:
            print(f"Names added to {image_path}.")
    except Exception as e:
        print(f"Error adding names to image: {str(e)}")

def add_names_to_all_images():
    get_data_from_csv_campers()
    for i in range(len(UUIDs)):
        camper_ID = UUIDs[i]
        name = f"{first_names[i]} {middle_names[i]} {last_names[i]}"
        image_path = f"static/QRs/{camper_ID}.png"
        add_name_to_image(image_path, name)
    print("Names added to all images successfully.")

def get_today_logins():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    logins = []
    try:
        with open(logins_csv_path, mode='r', newline='', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                if len(row) >= 3 and row[1].startswith(today):
                    action_text = "logged in" if row[2] == "login" else "logged out"
                    display_text = f"{get_name_from_ID(row[0])} {action_text} at {row[1][11:]}"
                    logins.append(display_text)
    except FileNotFoundError:
        print(f"The file {logins_csv_path} does not exist.")
    logins.reverse()
    return logins

get_data_from_csv_campers()

