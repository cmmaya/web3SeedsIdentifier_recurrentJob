import logging
import time
from datetime import datetime
import sys
import os
from bs4 import BeautifulSoup
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from prefect import flow, task
from dataclasses import dataclass, asdict
from typing import List, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from google_sheets import get_worksheet, write_rows

# Import Slack notifier if available
try:
    from tasks.notify import notify_slack
except ImportError:
    notify_slack = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CryptorankProject:
    """Data model for Cryptorank project"""
    name: str
    link: str
    funding_amount: str
    funding_type: str  # Seed, Grant, Pre-Seed, etc.
    backers: List[str]  # List of backer names
    funding_date: str
    description: Optional[str] = None
    website: Optional[str] = None
    twitter: Optional[str] = None
    linkedin: Optional[str] = None
    fetched_at: datetime = None

    def dict(self):
        # Convert to dict with serialized values
        result = asdict(self)
        result['backers'] = ', '.join(self.backers)
        if self.fetched_at:
            result['fetched_at'] = self.fetched_at.isoformat()
        return result


@task
def fetch_cryptorank_funding_rounds(pages=3):
    """Fetch funding rounds from Cryptorank"""
    base_url = "https://cryptorank.io/funding-rounds?page={}&rows=50"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    # Use direct path to correct driver
    driver_path = r"C:\Users\Camilo\.wdm\drivers\chromedriver\win64\136.0.7103.113\chromedriver-win32\chromedriver.exe"
    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    projects = []
    target_rounds = ["Seed", "Grant", "Pre-Seed", "Angel", "Extended Seed"]

    try:
        for page in range(1, pages + 1):
            url = base_url.format(page)
            logger.info(f"Opening Cryptorank URL: {url}")
            driver.get(url)
            time.sleep(5)  # Wait for the page to load

            # Find all rows in the table
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
            )
            
            # Extract the table content
            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.select("#root-container > div > div > section > div.sc-8b95f51a-0.sc-e739bd4e-0.hOzXIj.bxDZvl > div.sc-7216fc15-0.lbdGOI > div > div.sc-a3162eff-0.glHxUG > table > tbody > tr")
            
            logger.info(f"Found {len(rows)} rows on page {page}")
            
            for row in rows:
                try:
                    # Check if the funding type is one of our targets
                    funding_type_cell = row.select_one("td:nth-child(3) p")
                    if not funding_type_cell:
                        continue
                        
                    funding_type = funding_type_cell.text.strip()
                    
                    if funding_type not in target_rounds:
                        continue
                    
                    # Extract project name and link
                    link_element = row.select_one("td:first-child a.sc-bc80ddda-6")
                    if not link_element:
                        continue
                        
                    project_link = link_element.get("href", "")
                    if not project_link:
                        continue
                        
                    project_name = link_element.select_one(".name").text.strip() if link_element.select_one(".name") else ""
                    
                    # Extract funding amount
                    funding_amount = row.select_one("td:nth-child(2) p").text.strip() if row.select_one("td:nth-child(2) p") else ""
                    
                    # Extract funding date
                    funding_date = row.select_one("td:nth-child(5) p").text.strip() if row.select_one("td:nth-child(5) p") else ""
                    
                    # Extract backers
                    backers_cell = row.select_one("td:nth-child(4)")
                    backers = []
                    if backers_cell:
                        backer_links = backers_cell.select("a")
                        for backer_link in backer_links:
                            backer_name = backer_link.select_one("span")
                            if backer_name:
                                backers.append(backer_name.text.strip())
                    
                    # Construct the detail page URL (replace 'ico' with 'price')
                    detail_url = "https://cryptorank.io" + project_link.replace("/ico/", "/price/")
                    
                    logger.info(f"Found {funding_type} project: {project_name} ({detail_url})")
                    
                    # Add basic project info to our list
                    project = CryptorankProject(
                        name=project_name,
                        link=detail_url,
                        funding_amount=funding_amount,
                        funding_type=funding_type,
                        backers=backers,
                        funding_date=funding_date,
                        fetched_at=datetime.utcnow()
                    )
                    
                    projects.append(project)
                
                except Exception as e:
                    logger.warning(f"Error processing row: {e}")
                    continue
            
            # Sleep before moving to the next page to avoid rate limiting
            time.sleep(2)
    
    except Exception as e:
        logger.error(f"Error fetching funding rounds: {e}")
    
    finally:
        driver.quit()
    
    logger.info(f"Found {len(projects)} projects with target funding rounds")
    return projects


@task
def fetch_project_details(projects):
    """Fetch additional details for each project"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    driver_path = r"C:\Users\Camilo\.wdm\drivers\chromedriver\win64\136.0.7103.113\chromedriver-win32\chromedriver.exe"
    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    enriched_projects = []

    try:
        for project in projects:
            try:
                logger.info(f"Fetching details for {project.name} from {project.link}")
                driver.get(project.link)
                time.sleep(3)  # Wait for the page to load
                
                # Get the page source
                soup = BeautifulSoup(driver.page_source, "html.parser")
                
                # Extract description
                description_div = soup.select_one("div.sc-933dbf49-0 div.sc-933dbf49-2 p")
                if description_div:
                    project.description = description_div.text.strip()
                
                # Extract links (website, Twitter, LinkedIn)
                links_div = soup.select_one("div.links")
                if links_div:
                    links = links_div.select("a.styles_coin_social_link_item__SAH_3")
                    for link in links:
                        href = link.get("href", "")
                        span_text = link.select_one("span")
                        if span_text:
                            link_type = span_text.text.strip().lower()
                            
                            if "website" in link_type and href:
                                project.website = href
                            elif any(x in link_type for x in ["x", "twitter"]) and href:
                                project.twitter = href
                            elif "linkedin" in link_type and href:
                                project.linkedin = href
                
                # Get additional backers if they weren't all visible in the table
                funds_div = soup.select_one("div.investors")
                if funds_div:
                    backer_links = funds_div.select("a")
                    for backer_link in backer_links:
                        backer_name_elem = backer_link.select_one("p")
                        if backer_name_elem:
                            backer_name = backer_name_elem.text.strip()
                            if backer_name and backer_name not in project.backers:
                                project.backers.append(backer_name)
                
                enriched_projects.append(project)
                logger.info(f"✅ Successfully fetched details for {project.name}")
                
            except Exception as e:
                logger.warning(f"Error fetching details for {project.name}: {e}")
                enriched_projects.append(project)  # Add the project even if we couldn't get details
            
            # Sleep to avoid rate limiting
            time.sleep(1)
    
    except Exception as e:
        logger.error(f"Error in fetch_project_details: {e}")
    
    finally:
        driver.quit()
    
    return enriched_projects


@task
def store_cryptorank_projects(projects):
    """Store projects in Google Sheets"""
    if not projects:
        logger.info("No Cryptorank projects to store.")
        return []

    headers = ["name", "link", "funding_amount", "funding_type", "backers", 
              "funding_date", "description", "website", "twitter", "linkedin", "fetched_at"]
    
    ws = get_worksheet("cryptorank")
    existing_names = set()
    
    try:
        existing_records = ws.get_all_records()
        existing_names = set(row['name'].strip().lower() for row in existing_records if row.get('name'))
    except Exception as e:
        logger.warning(f"Could not get existing records: {e}")
    
    unique_projects = []
    for p in projects:
        if p.name.strip().lower() in existing_names:
            logger.info(f"⏩ Skipping duplicate project: {p.name}")
            continue
        unique_projects.append(p)

    rows = [p.dict() for p in unique_projects]

    if not rows:
        logger.info("🟡 No new unique Cryptorank projects to insert.")
        return []

    write_rows("cryptorank", rows, headers)
    logger.info(f"✅ {len(rows)} unique Cryptorank projects written to Google Sheets.")
    return unique_projects


@task
def notify_slack_if_available(projects):
    """Send notifications to Slack for new projects"""
    if not projects:
        logger.info("ℹ️ No new projects to notify.")
        return

    if not notify_slack:
        logger.warning("⚠️ Slack notifier not available.")
        return

    for project in projects:
        message = (f":money_with_wings: New {project.funding_type} round: *{project.name}* - {project.funding_amount}\n"
                  f"Backers: {', '.join(project.backers) if project.backers else 'N/A'}\n"
                  f"<{project.link}>")
        notify_slack.fn(message)
        logger.info(f"📨 Notified: {project.name}")


@flow(name="Cryptorank Funding Flow")
def run_cryptorank_flow(pages=3):
    """Main flow to run the Cryptorank scraper"""
    projects = fetch_cryptorank_funding_rounds(pages)
    enriched_projects = fetch_project_details(projects)
    stored = store_cryptorank_projects(enriched_projects)
    notify_slack_if_available(stored)
    logger.info(f"🎯 Flow complete. {len(stored)} new projects processed.")

if __name__ == "__main__":
    run_cryptorank_flow()