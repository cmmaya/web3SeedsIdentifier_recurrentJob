import os
import re
import sys
import requests
from datetime import datetime
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from prefect import flow, task

# Add parent directory to path so we can import tasks
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tasks.notify import notify_slack

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase - adjust the path as needed for your project structure
FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "web3identifier-firebase-adminsdk-fbsvc-894c77946c.json")

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()

@task
def fetch_seed_startups():
    """Fetch seed stage blockchain startups from Crunchbase API"""
    url = "https://api.crunchbase.com/api/v4/graphql"
    query = '''
    query {
      organizations(filter: {categories: ["blockchain"], stage: ["seed"]}) { 
        items { 
          uuid 
          name 
          short_description 
          homepage_url 
        } 
      }
    }
    '''
    
    headers = {"X-Cb-User-Key": os.getenv("CRUNCHBASE_API_KEY")}
    
    try:
        logger.info("Fetching data from Crunchbase API")
        resp = requests.post(url, json={"query": query}, headers=headers)
        resp.raise_for_status()  # Raise exception for HTTP errors
        
        data = resp.json()
        items = data["data"]["organizations"]["items"]
        logger.info(f"Successfully fetched {len(items)} organizations")
        return items
    except Exception as e:
        logger.error(f"Error fetching from Crunchbase API: {e}")
        return []

@task
def store_orgs_in_firestore(items):
    """Store organizations in Firestore database"""
    if not items:
        logger.warning("No organizations to store in Firestore")
        return []
    
    new_orgs = []
    collection_ref = db.collection('crunchbase_orgs')
    
    for org in items:
        try:
            # Use UUID as document ID (it's already a safe identifier)
            doc_id = org["uuid"]
            
            # In case the UUID has invalid characters (shouldn't happen but just to be safe)
            if not re.match(r'^[a-zA-Z0-9_-]+$', doc_id):
                doc_id = re.sub(r'[^\w-]', '', doc_id)
            
            doc_ref = collection_ref.document(doc_id)
            
            # Check if document already exists
            doc = doc_ref.get()
            if not doc.exists:
                org_data = {
                    "uuid": org["uuid"],
                    "name": org["name"],
                    "url": org.get("homepage_url", ""),
                    "description": org.get("short_description", ""),
                    "fetched_at": datetime.utcnow()
                }
                
                doc_ref.set(org_data)
                logger.info(f"Organization '{org['name']}' inserted successfully")
                new_orgs.append(org)
            else:
                logger.info(f"Organization '{org['name']}' already exists")
                
        except Exception as e:
            logger.error(f"Error storing organization '{org.get('name', 'Unknown')}': {e}")
            # Try with auto-generated ID if there's an issue
            try:
                auto_doc_ref = collection_ref.document()  # Let Firestore generate an ID
                org_data = {
                    "uuid": org["uuid"],
                    "name": org["name"],
                    "url": org.get("homepage_url", ""),
                    "description": org.get("short_description", ""),
                    "fetched_at": datetime.utcnow()
                }
                auto_doc_ref.set(org_data)
                logger.info(f"Organization '{org['name']}' inserted with auto-generated ID")
                new_orgs.append(org)
            except Exception as e2:
                logger.error(f"Failed to store organization '{org.get('name', 'Unknown')}' with auto-generated ID: {e2}")
    
    logger.info(f"Successfully stored {len(new_orgs)} new organizations")
    return new_orgs

@task
def prepare_slack_notifications(new_orgs):
    """Prepare Slack notification messages for new organizations"""
    if not new_orgs:
        return "No new blockchain seed startups found."
    
    # Create a summary message
    message = f":rocket: *{len(new_orgs)} New Blockchain Seed Startups*\n\n"
    
    # Add details for each new organization
    for i, org in enumerate(new_orgs, 1):
        name = org.get("name", "Unnamed")
        url = org.get("homepage_url", "No URL")
        desc = org.get("short_description", "No description")
        
        # Format the organization details
        org_details = f"*{i}. {name}*\n"
        if url:
            org_details += f"<{url}|Website> | "
        org_details += f"{desc[:100]}{'...' if len(desc) > 100 else ''}\n\n"
        
        message += org_details
        
        # If the message gets too long, add a summary and stop
        if len(message) > 3000:  # Slack has message size limits
            remaining = len(new_orgs) - i
            if remaining > 0:
                message += f"_...and {remaining} more organizations._"
            break
    
    return message

@flow(name="Crunchbase Seed Startups")
def run_flow():
    """Main flow to fetch and store seed stage blockchain startups"""
    items = fetch_seed_startups()
    new_orgs = store_orgs_in_firestore(items)
    
    # Prepare and send Slack notification
    slack_message = prepare_slack_notifications(new_orgs)
    notify_slack(slack_message)

if __name__ == "__main__":
    run_flow()