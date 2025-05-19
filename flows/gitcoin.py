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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from prefect import flow, task

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import GitcoinCheckerProject
from google_sheets import get_worksheet, write_rows


try:
    from tasks.notify import notify_slack
except ImportError:
    notify_slack = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@task
def fetch_gitcoin_checker_projects():
    url = "https://checker.gitcoin.co/public/projects/list"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    projects = []

    try:
        logger.info(f"Opening Gitcoin Checker URL: {url}")
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.container.py-3"))
        )
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        project_cards = soup.select("div.container.py-3 > div.mb-5.d-flex")
        logger.info(f"Found {len(project_cards)} project cards.")

        for card in project_cards:
            try:
                name_element = card.select_one('a.text-primary')
                name = name_element.text.strip() if name_element else "Unknown Project"
                project_url = name_element['href'] if name_element and name_element.has_attr('href') else ""
                if project_url and not project_url.startswith("http"):
                    project_url = "https://checker.gitcoin.co" + project_url

                description = card.select_one('div.text-xs')
                description = description.text.strip() if description else ""

                img_element = card.select_one('img')
                image_url = img_element['src'] if img_element and img_element.has_attr('src') else ""

                website, twitter, github = "", "", ""
                for link_element in card.select('div.small.d-flex a[target="_blank"]'):
                    href = link_element['href']
                    svg = str(link_element.select_one('svg'))
                    if 'bi-globe' in svg:
                        website = href
                    elif 'bi-twitter' in svg:
                        twitter = href
                    elif 'bi-github' in svg:
                        github = href

                created_at_element = card.select_one('div.text-muted.font-italic.small')
                created_at_text = created_at_element.text.strip() if created_at_element else ""

                project = GitcoinCheckerProject(
                    name=name,
                    description=description,
                    project_url=project_url,
                    website=website,
                    twitter=twitter,
                    github=github,
                    image_url=image_url,
                    created_at_text=created_at_text,
                    fetched_at=datetime.utcnow()
                )
                projects.append(project)
                logger.info(f"✓ Scraped project: {name}")

            except Exception as e:
                logger.warning(f"Failed to parse a project card: {e}")

    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
    finally:
        driver.quit()

    logger.info(f"✅ Total projects scraped: {len(projects)}")
    return projects

@task
def store_gitcoin_checker_projects(projects):
    if not projects:
        logger.info("No projects to store.")
        return []

    headers = [
        "name", "description", "project_url", "website", "twitter",
        "github", "image_url", "created_at_text", "fetched_at"
    ]

    ws = get_worksheet("gitcoin")
    existing_names = set(row['name'].strip().lower() for row in ws.get_all_records() if row.get('name'))

    unique_projects = []
    for p in projects:
        if p.name.strip().lower() in existing_names:
            logger.info(f"⏩ Skipping duplicate project name: {p.name}")
            continue
        unique_projects.append(p)

    rows = []
    for p in unique_projects:
        row = p.dict()
        row["fetched_at"] = row["fetched_at"].isoformat()
        rows.append(row)

    if not rows:
        logger.info("🟡 No new unique Gitcoin Checker projects to insert.")
        return []

    write_rows("gitcoin", rows, headers)
    logger.info(f"✅ {len(rows)} Gitcoin Checker projects written to Google Sheets.")
    return unique_projects

@task
def notify_new_gitcoin_checker_projects(projects):
    if not projects:
        logger.info("ℹ️ No new projects to notify.")
        return

    if not notify_slack:
        logger.warning("⚠️ Slack notifier not available.")
        return

    for project in projects:
        message = f":large_green_circle: New Gitcoin Checker project: *{project.name}*\n<{project.project_url}>"
        if project.description:
            message += f"\n_{project.description}_"
        if project.website:
            message += f"\n:globe_with_meridians: {project.website}"
        if project.twitter:
            message += f"\n:bird: {project.twitter}"
        if project.github:
            message += f"\n:octocat: {project.github}"

        notify_slack.fn(message)
        logger.info(f"📨 Notified: {project.name}")


@flow(name="Gitcoin Checker Projects Flow")
def run_gitcoin_checker_flow():
    projects = fetch_gitcoin_checker_projects()
    new_projects = store_gitcoin_checker_projects(projects)
    notify_new_gitcoin_checker_projects(new_projects)
    logger.info(f"🎯 Flow complete. {len(new_projects)} new projects processed.")


if __name__ == "__main__":
    run_gitcoin_checker_flow()
