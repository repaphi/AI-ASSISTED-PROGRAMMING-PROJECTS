import json
import uuid
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PROJECTS_FILE = DATA_DIR / "projects.json"


def ensure_storage():
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text("[]", encoding="utf-8")


def load_projects():
    ensure_storage()
    try:
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_projects(projects):
    ensure_storage()
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2), encoding="utf-8")


def new_project_id():
    return f"PRJ-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def save_uploaded_files(project_id, files):
    ensure_storage()
    saved = []
    project_upload_dir = UPLOAD_DIR / project_id
    project_upload_dir.mkdir(exist_ok=True)

    for file in files or []:
        safe_name = Path(file.name).name.replace("\\", "_").replace("/", "_")
        target = project_upload_dir / safe_name
        target.write_bytes(file.getbuffer())
        saved.append(
            {
                "name": safe_name,
                "path": str(target),
                "size_bytes": target.stat().st_size,
            }
        )
    return saved


def upsert_project(project):
    projects = load_projects()
    for index, existing in enumerate(projects):
        if existing["id"] == project["id"]:
            projects[index] = project
            save_projects(projects)
            return project
    projects.append(project)
    save_projects(projects)
    return project


def get_project(project_id):
    for project in load_projects():
        if project["id"] == project_id:
            return project
    return None
