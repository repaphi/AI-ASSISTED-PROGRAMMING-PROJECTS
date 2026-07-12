import base64
import csv
import io
import json
import mimetypes
import os
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from storage import get_project, load_projects, new_project_id, save_projects, upsert_project, UPLOAD_DIR
from ui import INDEX_HTML


HOST = "127.0.0.1"
PORT = 8000


def open_app_in_browser(url):
    try:
        os.startfile(url)
        return
    except Exception:
        pass
    webbrowser.open(url, new=2)


def now():
    return datetime.now().isoformat(timespec="seconds")


def json_bytes(data):
    return json.dumps(data, indent=2).encode("utf-8")


def clean_filename(name):
    return Path(name).name.replace("\\", "_").replace("/", "_")


def save_base64_uploads(project_id, uploads):
    saved = []
    project_dir = UPLOAD_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    for item in uploads or []:
        name = clean_filename(item.get("name", "upload.bin"))
        target = project_dir / name
        target.write_bytes(base64.b64decode(item.get("data", "")))
        saved.append({"name": name, "path": str(target), "size_bytes": target.stat().st_size})
    return saved


def flatten_project(project):
    client = project.get("client", {})
    info = project.get("project", {})
    location = project.get("location", {})
    budget = project.get("budget", {})
    return {
        "id": project.get("id", ""),
        "status": project.get("status", ""),
        "created_at": project.get("created_at", ""),
        "updated_at": project.get("updated_at", ""),
        "client_name": client.get("full_name", ""),
        "email": client.get("email", ""),
        "phone": client.get("phone", ""),
        "client_type": client.get("client_type", ""),
        "project_title": info.get("title", ""),
        "project_type": info.get("type", ""),
        "priority": info.get("priority", ""),
        "stage": info.get("stage", ""),
        "country": location.get("country", ""),
        "region": location.get("region", ""),
        "city": location.get("city", ""),
        "budget_range": budget.get("range", ""),
        "target_completion": info.get("target_completion_date", ""),
        "uploaded_files": len(project.get("uploads", [])),
    }


def projects_csv(projects):
    rows = [flatten_project(project) for project in projects]
    output = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["id"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def pdf_escape(text):
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def simple_pdf(project):
    lines = [
        "BuildScope Project Requirement Summary",
        "Requirement collection only. Licensed professional review and approval required.",
        f"Project ID: {project.get('id', '')}",
        f"Status: {project.get('status', '')}",
        f"Created: {project.get('created_at', '')}",
        "",
    ]
    for section in ["client", "project", "location", "site", "environment", "technical", "budget"]:
        lines.append(section.title())
        values = project.get(section, {})
        for key, value in values.items():
            lines.append(f"{key.replace('_', ' ').title()}: {value}")
        lines.append("")
    lines.append("Uploaded Files")
    for file in project.get("uploads", []):
        lines.append(f"- {file.get('name')} ({file.get('size_bytes', 0)} bytes)")
    lines.append("")
    lines.append("Internal Notes")
    for note in project.get("internal_notes", []):
        lines.append(f"- {note.get('created_at')}: {note.get('text')}")

    y = 760
    content = ["BT", "/F1 11 Tf", "50 760 Td"]
    for line in lines:
        safe = pdf_escape(line[:105])
        content.append(f"({safe}) Tj")
        content.append("0 -15 Td")
        y -= 15
        if y < 45:
            content.append("ET")
            content.append("BT /F1 11 Tf 50 760 Td")
            y = 760
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("ascii"))
    return bytes(pdf)


class AppHandler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="text/plain", filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/projects":
            self.send(200, json_bytes(load_projects()), "application/json")
            return
        if path == "/api/export.csv":
            self.send(200, projects_csv(load_projects()), "text/csv", "project_submissions.csv")
            return
        if path.startswith("/api/project/") and path.endswith(".pdf"):
            project_id = path.removeprefix("/api/project/").removesuffix(".pdf")
            project = get_project(project_id)
            if not project:
                self.send(404, b"Project not found")
                return
            self.send(200, simple_pdf(project), "application/pdf", f"{project_id}.pdf")
            return
        if path.startswith("/api/download/"):
            parts = path.split("/")
            if len(parts) >= 5:
                project_id = parts[3]
                name = clean_filename(unquote(parts[4]))
                target = UPLOAD_DIR / project_id / name
                if target.exists():
                    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                    self.send(200, target.read_bytes(), content_type, target.name)
                    return
            self.send(404, b"File not found")
            return
        self.send(404, b"Not found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/projects":
            project = self.read_json()
            uploads = project.pop("new_uploads", [])
            is_new = not project.get("id")
            if is_new:
                project["id"] = new_project_id()
                project["created_at"] = now()
                project.setdefault("internal_notes", [])
            project["updated_at"] = now()
            project.setdefault("uploads", [])
            project["uploads"].extend(save_base64_uploads(project["id"], uploads))
            upsert_project(project)
            self.send(200, json_bytes(project), "application/json")
            return
        if path.startswith("/api/project/") and path.endswith("/admin"):
            project_id = path.removeprefix("/api/project/").removesuffix("/admin")
            project = get_project(project_id)
            if not project:
                self.send(404, b"Project not found")
                return
            data = self.read_json()
            project["status"] = data.get("status", project.get("status", "Submitted"))
            project["updated_at"] = now()
            note = data.get("note", "").strip()
            if note:
                project.setdefault("internal_notes", []).append({"created_at": now(), "text": note})
            upsert_project(project)
            self.send(200, json_bytes(project), "application/json")
            return
        self.send(404, b"Not found")

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def run():
    url = f"http://{HOST}:{PORT}"
    try:
        server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    except OSError as error:
        print("")
        print("BuildScope is already running or port 8000 is busy.", flush=True)
        print(f"Reason: {error}", flush=True)
        print(f"Opening the app page now: {url}", flush=True)
        open_app_in_browser(url)
        return

    print("", flush=True)
    print("BuildScope Consultation Portal is running.", flush=True)
    print(f"Open this link in your browser: {url}", flush=True)
    print("Keep this terminal open. Press Ctrl+C here to stop the app.", flush=True)
    threading.Timer(0.5, lambda: open_app_in_browser(url)).start()
    server.serve_forever()


if __name__ == "__main__":
    run()
