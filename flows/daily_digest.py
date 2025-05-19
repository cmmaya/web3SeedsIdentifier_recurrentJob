from datetime import datetime, timedelta
import logging
import sys
import os
import firebase_admin
from firebase_admin import credentials, firestore
from prefect import flow, task

# Add parent directory to path so we can import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tasks.notify import notify_slack
from config import FIREBASE_SERVICE_ACCOUNT_PATH

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)
db = firestore.client()

@task
def get_top5():
    """
    Get the top 5 projects by score from the projects collection.
    
    Returns:
        list: A list of formatted strings describing the top projects
    """
    logger.info("Fetching top 5 projects by score")
    
    # Query Firestore for top 5 projects ordered by score descending
    projects_ref = db.collection('projects')
    query = projects_ref.order_by('score', direction=firestore.Query.DESCENDING).limit(5)
    
    top_projects = []
    for doc in query.stream():
        project = doc.to_dict()
        project_str = f"{project.get('name', 'Unnamed')} ({project.get('source', 'Unknown')}) – {project.get('score', 0)}"
        top_projects.append(project_str)
        logger.info(f"Found top project: {project_str}")
    
    return top_projects

@task
def format_message(items):
    """
    Format a list of project strings into a message for Slack.
    
    Args:
        items (list): List of strings describing projects
        
    Returns:
        str: A formatted message for Slack
    """
    if not items:
        return "🔔 *Daily Top 5 Projects:*\nNo projects found today."
    
    message = "🔔 *Daily Top 5 Projects:*\n" + "\n".join(f"- {i}" for i in items)
    logger.info(f"Formatted message: {message}")
    return message

@flow(name="Daily Digest")
def run_daily_digest():
    """
    Main flow to send daily digest of top projects.
    """
    logger.info("Starting daily digest flow")
    
    # Get top 5 projects
    top_projects = get_top5()
    
    # Format the message
    message = format_message(top_projects)
    
    # Send notification
    notify_slack.fn(message)
    
    logger.info("Daily digest flow completed successfully")

if __name__ == "__main__":
    # For local testing, run the flow directly
    run_daily_digest()