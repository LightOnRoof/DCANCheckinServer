import os
import hashlib
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
import csv
DEBUG = True
# Open and read the JSON file
with open('config.json', 'r', encoding="utf-8") as file:
    data = json.load(file)
FOLDER_ID = data.get('FOLDER_ID')
INPUT_SHEET_NAME = data.get('INPUT_SHEET_NAME', 'Form Responses 1')
SPREADSHEET_NAME = data.get("SPREADSHEET_NAME")
SPREADSHEET_ID = ''

Parent_data = []

# If you modify scopes, delete token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",'https://www.googleapis.com/auth/drive.readonly']

def get_service(api_name="sheets"):
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    if(api_name == "drive"):
        return build('drive', "v3", credentials=creds)
    return build("sheets", "v4", credentials=creds)

def sha1_hex(s: str) -> str:
    h = hashlib.sha1(s.encode("utf-8")).digest()
    # same mapping: (b + 256).toString(16).slice(-2)
    return "".join(f"{(b & 0xFF):02x}" for b in h)

def combine(a: list, b: list) -> list:
    """
    Given two lists of equal length:
      a = [a0, a1, ...]
      b = [[b0_0, b0_1...], [b1_0,...], ...]
    returns:
      [ [], [a0, *b[0]], [a1, *b[1]], ... ]
    """
    res = [[]]
    for ai, bi in zip(a, b):
        res.append([ai, *bi])
    return res


def process_parents(service):
    global Parent_data
    #ensure_sheets_exist(service, SPREADSHEET_ID, [PARENTS_SHEET_NAME])
    # 1) Read the form responses
    sheet = service.spreadsheets().values()
    full = sheet.get(spreadsheetId=SPREADSHEET_ID,
                     range=f"{INPUT_SHEET_NAME}!A:Z").execute().get("values", [])
    if not full or len(full) < 2:
        print("No form data.")
        return

    # 2) select columns 1–6 (zero-based indices 1..6)
    header, *rows = full
    selected = [row[1:7] for row in rows]

    # 3) generate SHA1 UUID per row
    uuids = [sha1_hex("".join(r)) for r in selected]

    # 4) combine + set header + drop the blank second row
    data = combine(uuids, selected)
    data[0] = ["UUID", "Email", "name_cn", "name_en", "relation", "phone_number", "wechat_id"]
    # remove the empty placeholder row
    data.pop(1)
    Parent_data = data
    with open("parents.csv", mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(data)
    # 5) write back to “parents”
    # body = {"values": data}
    # service.spreadsheets().values().update(
    #     spreadsheetId=SPREADSHEET_ID,
    #     range=f"{PARENTS_SHEET_NAME}!A1",
    #     valueInputOption="RAW",
    #     body=body
    # ).execute()
    # print(f"Wrote {len(data)} rows to {PARENTS_SHEET_NAME}")

def process_students(service):
    global Parent_data
    sheet = service.spreadsheets().values()
    full = sheet.get(spreadsheetId=SPREADSHEET_ID,
                     range=f"{INPUT_SHEET_NAME}!A:ZZ").execute().get("values", [])
    parents_full = Parent_data

    header, *rows = full
    # drop parents header
    _, *parents_data = parents_full

    # three kids: offsets 0,30,60 + columns 7..15
    offsets = [0, 30, 60]
    all_students = []
    all_uuids = []

    for off in offsets:
        # extract each child's data
        block = []
        for row in rows:
            # ensure row is long enough
            if len(row) >= off + 16:
                block.append(row[off + 7 : off + 16])  # 7..15 inclusive
            else:
                block.append([""] * 9)
        # drop header
        block = block[1:]

        # make UUIDs from first+last name
        uuids = [sha1_hex(r[0] + r[1]) for r in block]
        # append parent IDs
        for i, r in enumerate(block):
            father_id = mother_id = "N/A"
            parent = parents_data[i]
            # parent[4] is relation column (“父亲” vs something else)
            if parent[4] == "父亲":
                father_id = parent[0]
            else:
                mother_id = parent[0]
            r.extend([father_id, mother_id])

        all_students.extend(block)
        all_uuids.extend(uuids)

    # combine, drop empty rows
    combined = []
    for uid, stu in zip(all_uuids, all_students):
        first_name, last_name = stu[0], stu[1]
        if first_name.strip() or last_name.strip():
            combined.append([uid, *stu])

    # add header
    header_row = ["UUID","first_name","last_name","middle_name","gender",
                  "grade","school","lunch","is_allergy","allergy",
                  "Father_id","Mother_id"]
    combined.insert(0, header_row)
    # write to CSV for use
    with open("campers.csv", mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(combined)
    print(f"Generated data for {len(combined)} students.")
def find_spreadsheet_by_name(drive_service, folder_id, file_name):
    """
    Search for a Google Sheets file by name in a specific Drive folder.

    :param drive_service: Authorized Google Drive API service instance
    :param folder_id: The ID of the Google Drive folder to search in
    :param file_name: The name of the spreadsheet file (exact match)
    :return: File ID of the matched spreadsheet, or None if not found
    """
    query = (
        f"'{folder_id}' in parents and "
        "mimeType='application/vnd.google-apps.spreadsheet' and "
        "trashed=false and "
        f"name='{file_name}'"
    )

    response = drive_service.files().list(
        q=query,
        spaces='drive',
        fields="files(id, name)",
        pageSize=10  # adjust if needed
    ).execute()

    files = response.get('files', [])
    if not files:
        print(f"No spreadsheet named '{file_name}' found in folder ID {folder_id}")
        return None

    # Return the first match (or all if needed)
    file = files[0]
    print(f"Found: {file['name']} (ID: {file['id']})")
    return file['id']

def main():
    global SPREADSHEET_ID
    try:
        if(not DEBUG):
            service = get_service('drive')
            print("here ok")
            SPREADSHEET_ID = find_spreadsheet_by_name(service, FOLDER_ID, SPREADSHEET_NAME)
            print("here ok")
            print(SPREADSHEET_ID)
            service = get_service('sheets')
            process_parents(service)
            process_students(service)
        else:
            return
    except HttpError as e:
        print(f"API error: {e}")

if __name__ == "__main__":
    main()

