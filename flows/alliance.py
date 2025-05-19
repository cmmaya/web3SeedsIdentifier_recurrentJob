import logging
import time
from datetime import datetime
from bs4 import BeautifulSoup
import sys
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from prefect import flow, task

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import AllianceCompany
from google_sheets import get_worksheet, write_rows

try:
    from tasks.notify import notify_slack
except ImportError:
    notify_slack = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@task
def fetch_alliance_companies():
    url = "https://alliance.xyz/companies"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    companies = []

    try:
        logger.info(f"Opening Alliance.xyz URL: {url}")
        driver.get(url)
        time.sleep(5)

        # Scroll to load companies
        body = driver.find_element(By.TAG_NAME, "body")
        for _ in range(10):
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(1.5)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-theme='dark'][class*='css-1j7l9ft']"))
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")
        company_cards = soup.select("div.chakra-card")
        logger.info(f"Found {len(company_cards)} companies on Alliance.xyz")

        for card in company_cards:
            try:
                name_element = card.select_one("h2.chakra-heading")
                if not name_element:
                    logger.warning("Could not find company name element")
                    continue

                name = name_element.text.strip()

                # Get link from closest <a> ancestor or inside the card
                link_element = card.find_parent("a") or card.select_one("a")
                link = ""
                if link_element and link_element.has_attr("href"):
                    href = link_element["href"]
                    link = href if href.startswith("http") else "https://alliance.xyz" + href

                description_element = card.select_one("p.chakra-text")
                description = description_element.text.strip() if description_element else ""

                categories = [tag.text.strip() for tag in card.select("span.css-5lhp63")] or None

                company = AllianceCompany(
                    name=name,
                    link=link,
                    description=description,
                    categories=categories,
                    fetched_at=datetime.utcnow()
                )
                companies.append(company)
                logger.info(f"✓ Scraped company: {name} {categories if categories else ''}")

            except Exception as e:
                logger.warning(f"Failed to parse company card: {e}")

    except Exception as e:
        logger.error(f"Error fetching Alliance companies: {e}")
    finally:
        driver.quit()

    logger.info(f"✅ Total Alliance companies scraped: {len(companies)}")
    return companies


@task
def store_alliance_companies(companies):
    if not companies:
        logger.info("No Alliance companies to store.")
        return []

    headers = ["name", "link", "description", "categories", "fetched_at"]
    ws = get_worksheet("alliance")
    existing_names = set(row['name'].strip().lower() for row in ws.get_all_records() if row.get('name'))

    unique_companies = []
    for c in companies:
        if c.name.strip().lower() in existing_names:
            logger.info(f"⏩ Skipping duplicate company name: {c.name}")
            continue
        unique_companies.append(c)

    rows = []
    for c in unique_companies:
        row = c.dict()
        row["fetched_at"] = row["fetched_at"].isoformat()
        if row.get("categories") is None:
            row["categories"] = ""
        elif isinstance(row["categories"], list):
            row["categories"] = ", ".join(row["categories"])
        rows.append(row)

    if not rows:
        logger.info("🟡 No new unique Alliance companies to insert.")
        return []

    write_rows("alliance", rows, headers)
    logger.info(f"✅ {len(rows)} Alliance companies written to Google Sheets.")
    return unique_companies



@task
def notify_slack_if_available(companies):
    if not companies:
        logger.info("ℹ️ No new Alliance companies to notify.")
        return

    if not notify_slack:
        logger.warning("⚠️ Slack notifier not available.")
        return

    for company in companies:
        message = f":building_construction: New Alliance company: *{company.name}*\n<{company.link}>"
        if company.description:
            message += f"\n_{company.description}_"
        notify_slack.fn(message)
        logger.info(f"📨 Notified: {company.name}")


@flow(name="Alliance Companies Flow")
def run_alliance_flow():
    companies = fetch_alliance_companies()
    new_companies = store_alliance_companies(companies)
    notify_slack_if_available(new_companies)
    logger.info(f"🎯 Flow complete. {len(new_companies)} new Alliance companies stored.")


if __name__ == "__main__":
    run_alliance_flow()
