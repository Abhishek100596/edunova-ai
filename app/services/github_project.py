"""GitHub repository analysis for student projects (SSRF-safe, evidence-based)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from flask import current_app

_ALLOWED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".kts",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".json",
    ".xml",
    ".gradle",
    ".properties",
    ".sh",
    ".rb",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".r",
    ".ipynb",
}

_SKIP_DIR_PARTS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".venv",
    "venv",
    "target",
    ".gradle",
    ".idea",
    "coverage",
    "bin",
    "obj",
}

_BINARY_HINTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".jar",
    ".war",
    ".class",
    ".so",
    ".dll",
    ".exe",
    ".pyc",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp4",
    ".mp3",
}

_GITHUB_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

_MAX_FILES = 40
_MAX_FILE_BYTES = 80_000
_MAX_TOTAL_CHARS = 120_000


class GitHubAnalysisError(ValueError):
    """User-facing validation / fetch error."""


def parse_github_url(url: str) -> tuple[str, str]:
    raw = (url or "").strip()
    if not raw:
        raise GitHubAnalysisError("GitHub URL is required.")
    lowered = raw.lower()
    if lowered.startswith("file:") or "localhost" in lowered or "127.0.0.1" in lowered:
        raise GitHubAnalysisError("Only public GitHub repository URLs are allowed.")

    match = _GITHUB_RE.match(raw)
    if not match:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = (parsed.hostname or "").lower()
        if host not in {"github.com", "www.github.com"}:
            raise GitHubAnalysisError("URL must be a public github.com repository.")
        parts = [p for p in (parsed.path or "").split("/") if p]
        if len(parts) < 2:
            raise GitHubAnalysisError("Could not parse owner/repository from the URL.")
        owner, repo = parts[0], parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
    else:
        owner, repo = match.group("owner"), match.group("repo")

    if owner.lower() in {"settings", "orgs", "marketplace", "topics", "explore"}:
        raise GitHubAnalysisError("That does not look like a repository URL.")
    return owner, repo


def _api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "EDUNOVA-AI-College-Project",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = ""
    try:
        token = str(current_app.config.get("GITHUB_TOKEN") or "").strip()
    except RuntimeError:
        token = ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_json(url: str, *, timeout: int = 25) -> Any:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
        "api.github.com",
        "raw.githubusercontent.com",
    }:
        raise GitHubAnalysisError("Refusing non-GitHub network request.")
    req = urllib.request.Request(url, headers=_api_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if len(raw) > 2_000_000:
                raise GitHubAnalysisError("Remote response too large.")
            return json.loads(raw.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GitHubAnalysisError(
                "Repository not found or private. Only public repositories are supported."
            ) from exc
        if exc.code in {401, 403}:
            raise GitHubAnalysisError(
                "GitHub API rate limit or access denied. Try again later or set GITHUB_TOKEN."
            ) from exc
        raise GitHubAnalysisError(f"GitHub API error (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise GitHubAnalysisError("Could not reach GitHub. Check your network connection.") from exc


def _http_text(url: str, *, timeout: int = 25) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
        "api.github.com",
        "raw.githubusercontent.com",
    }:
        raise GitHubAnalysisError("Refusing non-GitHub network request.")
    req = urllib.request.Request(url, headers=_api_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(_MAX_FILE_BYTES + 1)
            if len(raw) > _MAX_FILE_BYTES:
                raw = raw[:_MAX_FILE_BYTES]
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise GitHubAnalysisError(f"Could not download file (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise GitHubAnalysisError("Network error while downloading repository files.") from exc


def _should_skip_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    if any(p in _SKIP_DIR_PARTS for p in parts):
        return True
    lower = path.lower()
    for ext in _BINARY_HINTS:
        if lower.endswith(ext):
            return True
    return False


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        if name.lower() in {"dockerfile", "makefile", "procfile", "gemfile", "rakefile"}:
            return f".{name.lower()}"
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _priority(path: str) -> int:
    name = path.lower()
    if name.endswith("readme.md") or name == "readme":
        return 0
    if name.endswith(
        (
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
            "cargo.toml",
        )
    ):
        return 1
    if name.endswith((".py", ".java", ".kt", ".ts", ".tsx", ".js", ".jsx")):
        return 2
    if name.endswith((".sql", ".html", ".css")):
        return 3
    return 5


def _detect_from_path(
    path: str, tech: set[str], languages: set[str], frameworks: set[str]
) -> None:
    lower = path.lower()
    ext = _ext(lower)
    lang_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".java": "Java",
        ".kt": "Kotlin",
        ".kts": "Kotlin",
        ".html": "HTML",
        ".css": "CSS",
        ".sql": "SQL",
        ".go": "Go",
        ".rs": "Rust",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".cpp": "C++",
        ".c": "C",
        ".r": "R",
        ".ipynb": "Python / Jupyter",
    }
    if ext in lang_map:
        languages.add(lang_map[ext])
        tech.add(lang_map[ext])
    if "package.json" in lower:
        frameworks.add("Node.js / npm")
        tech.add("Node.js")
    if "requirements.txt" in lower or "pyproject.toml" in lower:
        frameworks.add("Python packaging")
        tech.add("Python")
    if "dockerfile" in lower:
        tech.add("Docker")
        frameworks.add("Docker")
    if "build.gradle" in lower or lower.endswith(".kt"):
        frameworks.add("Android / Gradle" if lower.endswith(".kt") else "Gradle")
    if "manage.py" in lower:
        frameworks.add("Django")
    if "next.config" in lower:
        frameworks.add("Next.js")
    if "vite.config" in lower:
        frameworks.add("Vite")


def _scan_content(
    text: str, tech: set[str], frameworks: set[str], features: set[str]
) -> None:
    patterns = [
        (r"\bflask\b", "Flask", frameworks),
        (r"\bdjango\b", "Django", frameworks),
        (r"\bfastapi\b", "FastAPI", frameworks),
        (r"\breact\b", "React", frameworks),
        (r"\bvue\b", "Vue", frameworks),
        (r"\bspring\b", "Spring", frameworks),
        (r"\bsqlalchemy\b", "SQLAlchemy", frameworks),
        (r"\bscikit-learn\b|\bsklearn\b", "scikit-learn", tech),
        (r"\btensorflow\b|\bpytorch\b|\bkeras\b", "Machine Learning", tech),
        (r"\bpandas\b", "Pandas", tech),
        (r"\bnumpy\b", "NumPy", tech),
        (r"\bpostgresql\b|\bmysql\b|\bsqlite\b", "SQL database", tech),
        (r"\bjunit\b|\bpytest\b|\bjest\b", "Testing", features),
        (r"\bdocker\b", "Docker", frameworks),
        (r"\bgunicorn\b|\bnginx\b", "Deployment", features),
        (r"\brest\b|\bapi\b", "API", features),
    ]
    low = text.lower()
    for pattern, label, bucket in patterns:
        if re.search(pattern, low):
            bucket.add(label)
            tech.add(label)


def analyze_github_repository(url: str) -> dict[str, Any]:
    """Fetch public GitHub metadata + selected source files; evidence-based analysis."""
    owner, repo = parse_github_url(url)
    canonical = f"https://github.com/{owner}/{repo}"

    meta = _http_json(f"https://api.github.com/repos/{owner}/{repo}")
    default_branch = meta.get("default_branch") or "main"
    description = (meta.get("description") or "").strip()
    topics = meta.get("topics") or []
    language = meta.get("language")
    stars = meta.get("stargazers_count")
    license_name = None
    if isinstance(meta.get("license"), dict):
        license_name = meta["license"].get("spdx_id") or meta["license"].get("name")

    tree_payload = _http_json(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    )
    tree = tree_payload.get("tree") or []
    candidates: list[str] = []
    for node in tree:
        if node.get("type") != "blob":
            continue
        path = node.get("path") or ""
        size = int(node.get("size") or 0)
        if _should_skip_path(path) or size > _MAX_FILE_BYTES:
            continue
        ext = _ext(path)
        name = path.rsplit("/", 1)[-1].lower()
        if (
            ext in _ALLOWED_EXTENSIONS
            or name
            in {
                "dockerfile",
                "makefile",
                "procfile",
                "requirements.txt",
                "package.json",
            }
            or name.startswith("readme")
        ):
            candidates.append(path)

    candidates.sort(key=_priority)
    selected = candidates[:_MAX_FILES]

    found: dict[str, Any] = {
        "title": meta.get("name") or repo,
        "description": description or None,
        "languages": set(),
        "technologies": set(),
        "frameworks": set(),
        "libraries": set(),
        "features": set(),
        "files_reviewed": [],
        "readme_excerpt": None,
        "dependency_hints": [],
    }
    if language:
        found["languages"].add(str(language))
        found["technologies"].add(str(language))
    for t in topics:
        found["technologies"].add(str(t))

    total_chars = 0
    file_snippets: list[dict[str, str]] = []
    for path in selected:
        _detect_from_path(
            path, found["technologies"], found["languages"], found["frameworks"]
        )
        raw_url = (
            f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
        )
        try:
            text = _http_text(raw_url)
        except GitHubAnalysisError:
            continue
        if not text.strip():
            continue
        total_chars += len(text)
        if total_chars > _MAX_TOTAL_CHARS:
            break
        found["files_reviewed"].append(path)
        _scan_content(text, found["technologies"], found["frameworks"], found["features"])
        if path.lower().endswith("readme.md") or path.lower() == "readme":
            found["readme_excerpt"] = text[:2500]
        if path.lower().endswith(("requirements.txt", "package.json", "pyproject.toml")):
            found["dependency_hints"].append({"file": path, "excerpt": text[:1500]})
            for line in text.splitlines()[:80]:
                pkg = re.split(r"[=<>!~\s;#/]", line.strip(), maxsplit=1)[0].strip()
                if (
                    pkg
                    and not pkg.startswith(("{", "}", "[", "]", '"', "'", "/"))
                    and len(pkg) < 60
                ):
                    found["libraries"].add(pkg)
        file_snippets.append({"path": path, "excerpt": text[:1200]})

    languages = sorted(found["languages"])
    technologies = sorted(found["technologies"])
    frameworks = sorted(found["frameworks"])
    libraries = sorted(list(found["libraries"]))[:40]
    features = sorted(found["features"])

    architecture_clues: list[str] = []
    if any("app/" in f or "src/" in f for f in found["files_reviewed"]):
        architecture_clues.append("Source organized under app/ or src/ directories.")
    if any(f.endswith(".html") for f in found["files_reviewed"]):
        architecture_clues.append("Contains frontend HTML templates or pages.")
    if any(f.endswith((".py", ".java", ".kt", ".go")) for f in found["files_reviewed"]):
        architecture_clues.append("Contains backend / application source files.")
    if any("test" in f.lower() for f in found["files_reviewed"]):
        architecture_clues.append("Test-related paths were found.")
    if "Docker" in frameworks or any(
        "dockerfile" in f.lower() for f in found["files_reviewed"]
    ):
        architecture_clues.append("Deployment packaging via Docker appears present.")

    skills = sorted(
        set(
            languages
            + frameworks
            + [t for t in technologies if t in languages or t in frameworks]
        )
    )[:20]
    inferred: dict[str, Any] = {
        "complexity": (
            "moderate"
            if len(found["files_reviewed"]) >= 8
            else ("introductory" if len(found["files_reviewed"]) <= 3 else "focused")
        ),
        "skills_demonstrated": skills,
        "possible_skill_gaps": [],
        "resume_bullets": [],
        "notes": [],
    }
    if not description and not found["readme_excerpt"]:
        inferred["notes"].append(
            "Little prose documentation was found; analysis relies mainly on file names and code signals."
        )
    if "Testing" not in features:
        inferred["possible_skill_gaps"].append(
            "Automated tests were not clearly evidenced in sampled files."
        )
    stack_label = ", ".join((languages or technologies)[:4]) or "documented stack"
    if "API" in features:
        inferred["resume_bullets"].append(
            f"Built {found['title']} with API-oriented components using {', '.join(languages[:3]) or 'multiple languages'}."
        )
    else:
        inferred["resume_bullets"].append(
            f"Developed {found['title']} using {stack_label}."
        )
    if frameworks:
        inferred["resume_bullets"].append(
            f"Applied frameworks/libraries such as {', '.join(frameworks[:4])} based on repository evidence."
        )

    analysis = {
        "ok": True,
        "source_url": canonical,
        "owner": owner,
        "repo": repo,
        "default_branch": default_branch,
        "stars": stars,
        "license": license_name,
        "found_in_repository": {
            "title": found["title"],
            "description": description or None,
            "languages": languages,
            "technologies": technologies,
            "frameworks": frameworks,
            "libraries": libraries,
            "features": features,
            "architecture_clues": architecture_clues,
            "files_reviewed": found["files_reviewed"],
            "readme_excerpt": found["readme_excerpt"],
            "dependency_files": found["dependency_hints"],
            "topics": topics,
        },
        "inferred_from_code": inferred,
        "file_snippets": file_snippets[:12],
        "disclaimer": (
            "Analysis is based on publicly accessible GitHub metadata and a limited sample "
            "of text source files. It does not execute code and may miss private modules "
            "or unsampled paths."
        ),
    }

    summary_lines = [
        f"Repository: {owner}/{repo}",
        f"Title: {found['title']}",
    ]
    if description:
        summary_lines.append(f"GitHub description: {description}")
    if languages:
        summary_lines.append("Languages found: " + ", ".join(languages))
    if frameworks:
        summary_lines.append("Frameworks / tools found: " + ", ".join(frameworks))
    if features:
        summary_lines.append("Signals found: " + ", ".join(features))
    if architecture_clues:
        summary_lines.append("Architecture clues: " + " ".join(architecture_clues))
    summary_lines.append(
        f"Reviewed {len(found['files_reviewed'])} text files from branch '{default_branch}'."
    )
    analysis["summary_text"] = "\n".join(summary_lines)
    analysis["suggested_tech_stack"] = ", ".join(
        (frameworks or languages or technologies)[:12]
    )
    analysis["suggested_description"] = (
        description
        or (found["readme_excerpt"] or "").split("\n\n")[0][:500]
        or f"GitHub project {owner}/{repo} analyzed from public repository evidence."
    )
    return analysis


def apply_analysis_to_project_fields(analysis: dict[str, Any]) -> dict[str, str]:
    found = analysis.get("found_in_repository") or {}
    return {
        "title": str(found.get("title") or analysis.get("repo") or "GitHub Project")[:200],
        "description": str(analysis.get("suggested_description") or "")[:5000],
        "tech_stack": str(analysis.get("suggested_tech_stack") or "")[:500],
        "url": str(analysis.get("source_url") or "")[:500],
        "analysis_json": json.dumps(analysis),
    }
