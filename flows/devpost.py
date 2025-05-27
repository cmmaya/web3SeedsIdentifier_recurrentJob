import logging
import time
from datetime import datetime
import sys
import os
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from prefect import flow, task

# Only import ChromeDriverManager for local development
try:
    from webdriver_manager.chrome import ChromeDriverManager
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import DevpostWinner
from google_sheets import get_worksheet, write_rows

# Import Slack notifier if available
try:
    from tasks.notify import notify_slack
except ImportError:
    notify_slack = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_chrome_driver():
    """Create a Chrome WebDriver instance with proper configuration"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Check if we're in GitHub Actions or similar CI environment
    if os.getenv('GITHUB_ACTIONS') == 'true' or os.path.exists('/usr/local/bin/chromedriver'):
        # Use system ChromeDriver in CI environments
        logger.info("Using system ChromeDriver")
        service = Service('/usr/local/bin/chromedriver')
    elif USE_WEBDRIVER_MANAGER:
        # Use ChromeDriverManager for local development
        logger.info("Using ChromeDriverManager")
        service = Service(ChromeDriverManager().install())
    else:
        # Fallback to default ChromeDriver path
        logger.info("Using default ChromeDriver path")
        service = Service()
    
    return webdriver.Chrome(service=service, options=chrome_options)

@task
def fetch_devpost_blockchain_winners():
    url = "https://devpost.com/hackathons?search=blockchain&status[]=ended"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = create_chrome_driver()
    winners = []

    try:
        logger.info(f"Opening Devpost URL: {url}")
        driver.get(url)
        time.sleep(3)

        body = driver.find_element(By.TAG_NAME, "body")
        for _ in range(12):
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(1.2)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.hackathons-container"))
        )
        container = driver.find_element(By.CSS_SELECTOR, "div.hackathons-container")
        tiles = container.find_elements(By.CSS_SELECTOR, "a.tile-anchor")
        logger.info(f"Found {len(tiles)} hackathons.")

        hackathon_links = []
        for tile in tiles:
            try:
                if "View winners" in tile.text:
                    href = tile.get_attribute("href")
                    name = tile.find_element(By.CSS_SELECTOR, "h3").text.strip()
                    hackathon_links.append((name, href))
                    logger.info(f"✓ Hackathon with winners: {name}")
            except Exception as e:
                logger.warning(f"Tile parsing failed: {e}")

        for hackathon_name, hackathon_url in hackathon_links:
            try:
                logger.info(f"Opening hackathon: {hackathon_name}")
                driver.get(hackathon_url)
                time.sleep(3)

                try:
                    winner_button = driver.find_element(By.XPATH, "//a[contains(text(), 'View the winners')]")
                    project_gallery_url = winner_button.get_attribute("href")
                except:
                    logger.warning(f"No 'View the winners' button in: {hackathon_name}")
                    continue

                driver.get(project_gallery_url)
                time.sleep(3)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                items = soup.select("div.gallery-item")
                logger.info(f"{hackathon_name}: Found {len(items)} gallery items")

                for item in items:
                    if item.select_one("aside.entry-badge img.winner"):
                        title_el = item.select_one("h5")
                        link_el = item.select_one("a.block-wrapper-link")
                        if title_el and link_el:
                            title = title_el.text.strip()
                            link = link_el["href"]
                            winners.append(DevpostWinner(
                                title=title,
                                link=link,
                                hackathon=hackathon_name,
                                fetched_at=datetime.utcnow()
                            ))
                            logger.info(f"🏆 {title}")
            except Exception as e:
                logger.warning(f"Failed scraping {hackathon_name}: {e}")
    finally:
        driver.quit()

    logger.info(f"✅ Total winners scraped: {len(winners)}")
    return winners


@task
def store_devpost_winners(winners):
    if not winners:
        logger.info("No Devpost winners to store.")
        return []

    headers = ["title", "link", "hackathon", "fetched_at"]
    ws = get_worksheet("devpost")
    existing_titles = set(row['title'].strip().lower() for row in ws.get_all_records() if row.get('title'))

    unique_winners = []
    for w in winners:
        if w.title.strip().lower() in existing_titles:
            logger.info(f"⏩ Skipping duplicate title: {w.title}")
            continue
        unique_winners.append(w)

    rows = []
    for w in unique_winners:
        row = w.dict()
        row["fetched_at"] = row["fetched_at"].isoformat()
        rows.append(row)

    if not rows:
        logger.info("🟡 No new unique Devpost winners to insert.")
        return []

    write_rows("devpost", rows, headers)
    logger.info(f"✅ {len(rows)} unique Devpost winners written to Google Sheets.")
    return unique_winners


@task
def notify_slack_if_available(projects):
    if not projects:
        logger.info("ℹ️ No new winners to notify.")
        return

    if not notify_slack:
        logger.warning("⚠️ Slack notifier not available.")
        return

    for project in projects:
        message = f":trophy: New Devpost winner: *{project.title}* from *{project.hackathon}*\n<{project.link}>"
        notify_slack.fn(message)
        logger.info(f"📨 Notified: {project.title}")


@flow(name="Devpost Winners Flow")
def run_devpost_flow():
    winners = fetch_devpost_blockchain_winners()
    stored = store_devpost_winners(winners)
    notify_slack_if_available(stored)
    logger.info(f"🎯 Flow complete. {len(stored)} winners processed.")

if __name__ == "__main__":
    run_devpost_flow()
