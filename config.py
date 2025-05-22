import os
from dotenv import load_dotenv

load_dotenv()

# Google Sheets service account
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")

# Sheet IDs by flow
SPREADSHEETS = {
    "devpost": {
        "sheet_id": os.getenv("DEVPOST_SHEET_ID"),
        "worksheet_name": os.getenv("DEVPOST_WORKSHEET_NAME", "Sheet1")
    },
    "merge": {
        "sheet_id": os.getenv("MERGE_SHEET_ID"),
        "worksheet_name": os.getenv("MERGE_WORKSHEET_NAME", "Sheet1")
    },
    "gitcoin": {
        "sheet_id": os.getenv("GITCOIN_SHEET_ID"),
        "worksheet_name": os.getenv("GITCOIN_WORKSHEET_NAME", "Sheet1")
    }
    ,
    "ethglobal": {
        "sheet_id": os.getenv("ETHGLOBAL_SHEET_ID"),
        "worksheet_name": os.getenv("ETHGLOBAL_WORKSHEET_NAME", "Sheet1")
    }
    ,
    "alliance": {
        "sheet_id": os.getenv("ALLIANCE_SHEET_ID"),
        "worksheet_name": os.getenv("ALLIANCE_WORKSHEET_NAME", "Sheet1")
    }
    ,
    "cryptorank": {
        "sheet_id": os.getenv("CRYPTORANK_SHEET_ID"),
        "worksheet_name": os.getenv("CRYPTORANK_WORKSHEET_NAME", "Sheet1")
    }
    # Add other flows here
}
