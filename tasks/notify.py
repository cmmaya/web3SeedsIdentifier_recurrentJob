from prefect import task
import os
import requests
import logging

# Set up logging
logger = logging.getLogger(__name__)

@task
def notify_slack(message: str):
    """
    Send a notification to Slack using a webhook URL from environment variables.
    
    Args:
        message (str): The message to send to Slack
    """
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        logger.error("SLACK_WEBHOOK_URL environment variable not set")
        return
        
    try:
        response = requests.post(url, json={"text": message})
        if response.status_code == 200:
            logger.info(f"Slack notification sent successfully")
        else:
            logger.error(f"Failed to send Slack notification: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Error sending Slack notification: {e}")