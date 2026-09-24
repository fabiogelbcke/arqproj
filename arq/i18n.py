"""UI strings and formatting helpers (English and Brazilian Portuguese)."""

from __future__ import annotations

import os
from datetime import datetime

from .drive import DriveFile

STRINGS = {
    "en": {
        "portal": "Project portal",
        "stages": "Stages",
        "status.done": "Completed",
        "status.current": "In progress",
        "status.upcoming": "Upcoming",
        "files.one": "1 file",
        "files.many": "{n} files",
        "no_files": "No files yet",
        "updated": "Updated {date}",
        "last_updated": "Last updated",
        "not_found.title": "Project not found",
        "not_found.body": "This link may be incorrect or no longer active. Please check with your architect.",
        "error.title": "Something went wrong",
        "error.body": "We couldn't load this page. Please try again in a moment.",
        "landing.body": "Open the link you received to view your project.",
        "projects": "Projects",
    },
    "pt": {
        "portal": "Portal do projeto",
        "stages": "Etapas",
        "status.done": "Concluída",
        "status.current": "Em andamento",
        "status.upcoming": "Próxima",
        "files.one": "1 arquivo",
        "files.many": "{n} arquivos",
        "no_files": "Nenhum arquivo ainda",
        "updated": "Atualizado em {date}",
        "last_updated": "Última atualização",
        "not_found.title": "Projeto não encontrado",
        "not_found.body": "Este link pode estar incorreto ou não estar mais ativo. Fale com seu arquiteto.",
        "error.title": "Algo deu errado",
        "error.body": "Não foi possível carregar esta página. Tente novamente em instantes.",
        "landing.body": "Abra o link que você recebeu para ver seu projeto.",
        "projects": "Projetos",
    },
}

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "pt": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"],
}

NATIVE_LABELS = {
    "application/vnd.google-apps.document": "DOC",
    "application/vnd.google-apps.spreadsheet": "SHEET",
    "application/vnd.google-apps.presentation": "SLIDES",
    "application/vnd.google-apps.drawing": "DRAWING",
}


def lang() -> str:
    value = os.environ.get("SITE_LANG", "en").lower()
    return "pt" if value.startswith("pt") else "en"


def t(key: str, **kwargs) -> str:
    text = STRINGS[lang()].get(key) or STRINGS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def fmt_date(dt: datetime | None) -> str:
    if not dt:
        return ""
    return f"{dt.day} {MONTHS[lang()][dt.month - 1]} {dt.year}"


def fmt_size(n: int | None) -> str:
    if n is None:
        return ""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            text = f"{size:.0f}" if unit == "B" or size >= 100 else f"{size:.1f}"
            if lang() == "pt":
                text = text.replace(".", ",")
            return f"{text} {unit}"
        size /= 1024
    return ""


def fmt_files(n: int) -> str:
    return t("files.one") if n == 1 else t("files.many", n=n)


def type_label(f: DriveFile) -> str:
    if f.mime_type in NATIVE_LABELS:
        return NATIVE_LABELS[f.mime_type]
    if "." in f.name:
        ext = f.name.rsplit(".", 1)[1]
        if 1 <= len(ext) <= 5 and ext.isalnum():
            return ext.upper()
    return "FILE"
