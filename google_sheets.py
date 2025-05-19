import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import List, Dict, Any
from config import GOOGLE_SHEETS_CREDENTIALS_PATH, SPREADSHEETS
from datetime import datetime

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_client():
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_PATH, scope)
    return gspread.authorize(creds)

def get_worksheet(flow_name: str):
    config = SPREADSHEETS[flow_name]
    client = get_client()
    sheet = client.open_by_key(config["sheet_id"])
    return sheet.worksheet(config["worksheet_name"])

def write_rows(flow_name: str, rows: List[Dict[str, Any]], headers: List[str]):
    ws = get_worksheet(flow_name)

    # Read existing headers
    existing_headers = ws.row_values(1)
    if existing_headers != headers:
        ws.clear()
        ws.append_row(headers)

    existing_data = ws.get_all_values()
    current_row_count = len(existing_data)

    # Serialize datetimes to strings and align row order with headers
    def serialize(row):
        return [row.get(h, "") if not isinstance(row.get(h), datetime) 
                else row[h].isoformat() for h in headers]

    values = [serialize(row) for row in rows]

    # Write values after current data
    if values:
        ws.append_rows(values)

