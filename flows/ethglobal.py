import logging
import time
from datetime import datetime
import re
import sys
import os
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from prefect import flow, task

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import EthGlobalWinner
from google_sheets import get_worksheet, write_rows

try:
    from tasks.notify import notify_slack
except ImportError:
    notify_slack = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@task
def fetch_ethglobal_winners():
    url = "https://ethglobal.com/showcase/"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    winners = []

    try:
        logger.info(f"Opening ETHGlobal Showcase: {url}")
        driver.get(url)
        time.sleep(5)

        selectors = [
            "div[class*='ProjectCard']",
            "div[class*='project-card']",
            "div.showcase-grid > div",
            "div.showcase > div",
            "a[href*='/showcase/']",
            "div[class*='grid'] > div"
        ]

        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if not elements:
                continue
            logger.info(f"Using selector '{selector}' with {len(elements)} elements.")

            soup = BeautifulSoup(driver.page_source, "html.parser")
            cards = soup.select(selector)

            for card in cards:
                try:
                    title_el = (
                        card.select_one("h3") or
                        card.select_one("[class*='title']") or
                        card.select_one("div[class*='Title']") or
                        card.select_one("strong")
                    )
                    link_el = card.find("a", href=True)

                    if title_el and link_el:
                        full_title = title_el.text.strip()
                        link = link_el["href"]
                        if not link.startswith("http"):
                            link = "https://ethglobal.com" + link

                        # Parse title and description
                        # Get the first line as the title, and the rest as description
                        parts = full_title.split('\n', 1)
                        title = parts[0].strip()
                        description = parts[1].strip() if len(parts) > 1 else ""

                        winners.append(EthGlobalWinner(
                            title=title,
                            description=description,
                            link=link,
                            fetched_at=datetime.utcnow()
                        ))
                        logger.info(f"✓ Found ETHGlobal project: {title}")
                        if description:
                            logger.info(f"  Description: {description[:50]}...")

                except Exception as e:
                    logger.warning(f"Failed parsing ETHGlobal project card: {e}")
            if winners:
                break

        if not winners:
            logger.info("Fallback: scanning all a[href*='/showcase/']")
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/showcase/']")
            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.text.strip()
                    if "/showcase/" in href and text:
                        # Parse title and description for fallback as well
                        parts = text.split('\n', 1)
                        title = parts[0].strip()
                        description = parts[1].strip() if len(parts) > 1 else ""
                        
                        winners.append(EthGlobalWinner(
                            title=title,
                            description=description,
                            link=href,
                            fetched_at=datetime.utcnow()
                        ))
                        logger.info(f"✓ Found fallback ETHGlobal project: {title}")
                except:
                    continue

    except Exception as e:
        logger.error(f"Error scraping ETHGlobal: {e}")
    finally:
        driver.quit()

    logger.info(f"✅ Total ETHGlobal winners scraped: {len(winners)}")
    return winners


@task
def store_ethglobal_projects(projects):
    if not projects:
        logger.info("No projects to store.")
        return []

    headers = ["title", "description", "link", "fetched_at"]
    ws = get_worksheet("ethglobal")
    existing_titles = set(row['title'].strip().lower() for row in ws.get_all_records() if row.get('title'))

    unique_projects = []
    for p in projects:
        if p.title.strip().lower() in existing_titles:
            logger.info(f"⏩ Skipping duplicate title: {p.title}")
            continue
        unique_projects.append(p)

    rows = []
    for p in unique_projects:
        row = p.dict()
        row["fetched_at"] = row["fetched_at"].isoformat()
        rows.append(row)

    if not rows:
        logger.info("🟡 No new unique ETHGlobal projects to insert.")
        return []

    write_rows("ethglobal", rows, headers)
    logger.info(f"✅ {len(rows)} ETHGlobal projects written to Google Sheets.")
    return unique_projects



@task
def send_slack_notifications(projects):
    if not projects or not notify_slack:
        return

    for project in projects:
        message = f":trophy: New ETHGlobal winner: *{project.title}*"
        if project.description:
            message += f"\n_{project.description}_"
        message += f"\n<{project.link}>"
        
        notify_slack.fn(message)
        logger.info(f"📨 Notified: {project.title}")


@flow(name="ETHGlobal Winners Flow")
def run_ethglobal_flow():
    winners = fetch_ethglobal_winners()
    new_projects = store_ethglobal_projects(winners)
    send_slack_notifications(new_projects)
    logger.info(f"🎯 ETHGlobal flow complete. {len(new_projects)} winners processed.")


if __name__ == "__main__":
    run_ethglobal_flow()