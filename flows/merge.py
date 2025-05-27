from datetime import datetime 
import logging
import sys
import os
import re
from prefect import flow, task

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Project
from google_sheets import get_worksheet, write_rows

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SOURCE_SCORE = {
    'ETHGlobal': 3,
    'Devpost': 2,
    'GitcoinChecker': 4,
    'AllianceDAO': 3,
    'Alliance': 5,
    'Cryptorank': 5
}

def sanitize_document_id(text):
    if not text:
        return f"doc_{int(datetime.utcnow().timestamp() * 1000)}"
    sanitized = re.sub(r'[./#\[\]$]+', '_', text)
    sanitized = re.sub(r'\s+', '_', sanitized)
    if sanitized in ['.', '..']:
        sanitized = f"doc_{sanitized}"
    if len(sanitized.encode('utf-8')) > 500:
        sanitized = sanitized.encode('utf-8')[:500].decode('utf-8', 'ignore')
    return sanitized or f"doc_{int(datetime.utcnow().timestamp() * 1000)}"


@task
def merge_devpost():
    ws = get_worksheet("devpost")
    data = ws.get_all_records()
    projects = []
    for row in data:
        title = row.get("title")
        if not title:
            continue
        try:
            project = Project(
                id="devpost_" + sanitize_document_id(str(title).lower()),
                name=str(title),
                link=row.get('link', ''),
                source="Devpost",
                hackathon=row.get('hackathon', ''),
                score=SOURCE_SCORE['Devpost'],
                last_seen=datetime.utcnow()
            )
            projects.append(project)
        except Exception as e:
            logger.warning(f"⚠️ Skipping Devpost row: {e} | row: {row}")
    return projects


@task
def merge_gitcoin():
    ws = get_worksheet("gitcoin")
    data = ws.get_all_records()
    projects = []
    for row in data:
        name = row.get("name")
        if not name:
            continue
        try:
            project = Project(
                id="gitcoinchecker_" + sanitize_document_id(str(name).lower()),
                name=str(name),
                link=row.get('website') or row.get('github') or row.get('project_url', ''),
                source="GitcoinChecker",
                description=row.get('description', ''),
                score=SOURCE_SCORE['GitcoinChecker'],
                last_seen=datetime.utcnow()
            )
            projects.append(project)
        except Exception as e:
            logger.warning(f"⚠️ Skipping Gitcoin row: {e} | row: {row}")
    return projects


@task
def merge_ethglobal():
    ws = get_worksheet("ethglobal")
    data = ws.get_all_records()
    projects = []
    for row in data:
        title = row.get("title")
        if not title:
            continue
        try:
            project = Project(
                id="ethglobal_" + sanitize_document_id(str(title).lower()),
                name=str(title),
                link=row.get('link', ''),
                source="ETHGlobal",
                description=row.get('description', ''),
                score=SOURCE_SCORE['ETHGlobal'],
                last_seen=datetime.utcnow()
            )
            projects.append(project)
        except Exception as e:
            logger.warning(f"⚠️ Skipping ETHGlobal row: {e} | row: {row}")
    return projects


@task
def merge_alliance():
    ws = get_worksheet("alliance")
    data = ws.get_all_records()
    projects = []
    for row in data:
        name = row.get("name")
        if not name:
            continue
        try:
            project = Project(
                id="alliance_" + sanitize_document_id(str(name).lower()),
                name=str(name),
                link=row.get('link', ''),
                source="Alliance",
                description=row.get('description', ''),
                categories=row.get('categories', '').split(", ") if row.get('categories') else [],
                score=SOURCE_SCORE['Alliance'],
                last_seen=datetime.utcnow()
            )
            projects.append(project)
        except Exception as e:
            logger.warning(f"⚠️ Skipping Alliance row: {e} | row: {row}")
    return projects


@task
def store_merged_projects(projects):
    headers = ["id", "name", "link", "source", "description", "categories", "hackathon", "score", "last_seen"]
    ws = get_worksheet("merge")
    existing_ids = set(row['id'] for row in ws.get_all_records())

    new_rows = []
    for p in projects:
        if p.id in existing_ids:
            logger.info(f"⏩ Skipping duplicate ID: {p.id}")
            continue
        row = p.dict()
        row["categories"] = ", ".join(row.get("categories", [])) if isinstance(row.get("categories"), list) else ""
        row["last_seen"] = row["last_seen"].isoformat()
        new_rows.append(row)

    if new_rows:
        write_rows("merge", new_rows, headers)
    logger.info(f"✅ {len(new_rows)} new projects merged.")
    return len(new_rows)


@task
def merge_cryptorank():
    ws = get_worksheet("cryptorank")
    data = ws.get_all_records()
    projects = []
    for row in data:
        name = row.get("name")
        if not name:
            continue
        try:
            project = Project(
                id="cryptorank_" + sanitize_document_id(str(name).lower()),
                name=name,
                link=row.get("link", ""),
                source="Cryptorank",
                description=row.get("description", ""),
                score=SOURCE_SCORE["Cryptorank"],
                last_seen=datetime.utcnow()
            )
            projects.append(project)
        except Exception as e:
            logger.warning(f"⚠️ Skipping Cryptorank row: {e} | row: {row}")
    return projects

@flow(name="Merge All Sources Flow")
def run_merge_flow():
    devpost = merge_devpost()
    gitcoin = merge_gitcoin()
    ethglobal = merge_ethglobal()
    alliance = merge_alliance()
    cryptorank = merge_cryptorank()

    all_projects = devpost + gitcoin + ethglobal + alliance + cryptorank
    count = store_merged_projects(all_projects)
    logger.info(f"🎯 Merge complete: {count} new projects stored.")


if __name__ == "__main__":
    run_merge_flow()
