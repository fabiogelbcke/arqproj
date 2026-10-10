"""UI strings and formatting helpers (English and Brazilian Portuguese)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .drive import NATIVE_PREFIX, DriveFile

STRINGS = {
    "en": {
        "portal": "Project portal",
        "theme.light": "Light mode",
        "theme.dark": "Dark mode",
        "stages": "Stages",
        "meeting.heading": "Meeting",
        "meeting.none": "No meeting scheduled",
        "meeting.default_title": "Project meeting · {project}",
        "meeting.calendar": "Add to Google Calendar",
        "meeting.apple": "Apple Calendar",
        "meeting.add": "Add to calendar",
        "meeting.location": "Location",
        "meeting.join": "Join meeting",
        "meeting.brasilia": "Brasília time",
        "cfg.invalid_meeting": "Meeting settings in {name} are invalid: {detail}",
        "status.done": "Completed",
        "status.current": "In progress",
        "status.upcoming": "Upcoming",
        "files.one": "1 file",
        "files.many": "{n} files",
        "new_files": "{n} new",
        "new": "New",
        "no_files": "No files yet",
        "updated": "Updated {date}",
        "last_updated": "Last updated",
        "previous_versions": "Previous versions ({n})",
        "not_found.title": "Project not found",
        "not_found.body": "This link may be incorrect or no longer active. Please check with your architect.",
        "error.title": "Something went wrong",
        "error.body": "We couldn't load this page. Please try again in a moment.",
        "landing.body": "Open the link you received to view your project.",
        "projects": "Projects",
        # Dashboard
        "dash.title": "Dashboard",
        "dash.login": "Sign in",
        "dash.password": "Password",
        "dash.wrong_password": "Wrong password.",
        "dash.logout": "Sign out",
        "dash.refresh": "Refresh from Drive",
        "dash.refreshed": "Reloaded from Drive.",
        "dash.project": "Project",
        "dash.stage": "Stage",
        "dash.updated": "Updated",
        "dash.files": "Files",
        "dash.link": "Client link",
        "dash.copy": "Copy",
        "dash.copied": "Copied",
        "dash.open": "Open",
        "dash.folder": "Drive folder",
        "dash.none": "No projects found in the root folder.",
        "dash.no_status": "No status",
        "dash.issues": "Needs attention",
        "warn.no_config": "No _project doc: the title comes from the folder name and there is no description.",
        "warn.guessable_link": "The link comes from the folder name and is easy to guess. Add a “Slug:” line with something random to _project.",
        "warn.stage_unmatched": "“Current stage: {value}” doesn't match any stage folder.",
        "warn.no_stages": "No stage folders yet.",
        "warn.root_files": "{n} file(s) directly in the project folder are not shown. Move them into a stage folder.",
        "warn.duplicate_slug": "“{other}” also asks for the link /{slug}, so that project is hidden. Change the “Slug:” in one of them.",
        "warn.slug_taken": "HIDDEN FROM CLIENTS: the link /{slug} already belongs to “{other}”. Give this project its own “Slug:” in _project (it was probably copied from another project).",
        "warn.folder_unreadable": "Couldn't open this folder: {reason}",
        "warn.stage_unreadable": "Couldn't open the stage folder “{stage}”: {reason}",
        "warn.config_unreadable": "Couldn't read {name}: {reason}",
        "warn.multiple_configs": "There are {n} config files in this folder; using “{used}”. Delete the others.",
        "cfg.encoding": "{name} isn't saved as UTF-8 text, so accents may come out garbled. Re-save it as UTF-8 or use a Google Doc.",
        "cfg.duplicate_key": "“{key}:” appears more than once in {name}; the last one wins.",
        "cfg.key_in_description": "“{key}:” on line {line} of {name} is below the description text, so it's ignored. Move it up with the other fields.",
        "cfg.invalid_slug": "HIDDEN FROM CLIENTS: “Slug: {value}” isn't a valid link. Use only lowercase letters, numbers and hyphens, with no spaces or accents (e.g. casa-nova-7k2p).",
        "warn.duplicate_folder_name": "{n} project folders are named “{name}”. Rename them so they're easy to tell apart.",
        "warn.duplicate_stage": "More than one stage is numbered {stage}: {names}. Renumber one so the timeline order is clear.",
        "warn.duplicate_stage_name": "{n} stage folders are named “{name}”. Rename or number them.",
        "warn.stage_ambiguous": "“Current stage: {value}” matches more than one stage, so it's ignored and the status is worked out from the files. Renumber the stages or use the stage name.",
        "err.not_found": "not found or not shared with the site (a shortcut to a folder outside the shared root?)",
        "err.forbidden": "the site has no permission to read it",
        "err.other": "unexpected error ({detail})",
        "dash.attention": "{n} of {total} projects need attention",
        "dash.root_error": "Couldn't read the root Drive folder: {reason}",
        "dash.hidden": "Hidden",
    },
    "pt": {
        "portal": "Portal do projeto",
        "theme.light": "Modo claro",
        "theme.dark": "Modo escuro",
        "stages": "Etapas",
        "meeting.heading": "Reunião",
        "meeting.none": "Não há reuniões agendadas",
        "meeting.default_title": "Reunião do projeto · {project}",
        "meeting.calendar": "Adicionar ao Google Agenda",
        "meeting.apple": "Calendário da Apple",
        "meeting.add": "Adicionar à agenda",
        "meeting.location": "Local",
        "meeting.join": "Entrar na reunião",
        "meeting.brasilia": "horário de Brasília",
        "cfg.invalid_meeting": "A configuração da reunião em {name} é inválida. Confira a data e a hora de início, o fim posterior ao início e um link HTTPS válido.",
        "status.done": "Concluída",
        "status.current": "Em andamento",
        "status.upcoming": "Próxima",
        "files.one": "1 arquivo",
        "files.many": "{n} arquivos",
        "new_files": "{n} novo(s)",
        "new": "Novo",
        "no_files": "Nenhum arquivo ainda",
        "updated": "Atualizado em {date}",
        "last_updated": "Última atualização",
        "previous_versions": "Versões anteriores ({n})",
        "not_found.title": "Projeto não encontrado",
        "not_found.body": "Este link pode estar incorreto ou não estar mais ativo. Fale com seu arquiteto.",
        "error.title": "Algo deu errado",
        "error.body": "Não foi possível carregar esta página. Tente novamente em instantes.",
        "landing.body": "Abra o link que você recebeu para ver seu projeto.",
        "projects": "Projetos",
        # Dashboard
        "dash.title": "Painel",
        "dash.login": "Entrar",
        "dash.password": "Senha",
        "dash.wrong_password": "Senha incorreta.",
        "dash.logout": "Sair",
        "dash.refresh": "Atualizar do Drive",
        "dash.refreshed": "Dados recarregados do Drive.",
        "dash.project": "Projeto",
        "dash.stage": "Etapa",
        "dash.updated": "Atualizado",
        "dash.files": "Arquivos",
        "dash.link": "Link do cliente",
        "dash.copy": "Copiar",
        "dash.copied": "Copiado",
        "dash.open": "Abrir",
        "dash.folder": "Pasta no Drive",
        "dash.none": "Nenhum projeto encontrado na pasta raiz.",
        "dash.no_status": "Sem status",
        "dash.issues": "Precisa de atenção",
        "warn.no_config": "Sem documento _project: o título vem do nome da pasta e não há descrição.",
        "warn.guessable_link": "O link vem do nome da pasta e é fácil de adivinhar. Adicione uma linha “Slug:” com algo aleatório no _project.",
        "warn.stage_unmatched": "“Etapa atual: {value}” não corresponde a nenhuma pasta de etapa.",
        "warn.no_stages": "Nenhuma pasta de etapa ainda.",
        "warn.root_files": "{n} arquivo(s) soltos na pasta do projeto não aparecem. Mova-os para uma pasta de etapa.",
        "warn.duplicate_slug": "“{other}” também usa o link /{slug}, então aquele projeto está oculto. Troque o “Slug:” de um deles.",
        "warn.slug_taken": "OCULTO PARA O CLIENTE: o link /{slug} já pertence a “{other}”. Dê a este projeto um “Slug:” próprio no _project (provavelmente foi copiado de outro projeto).",
        "warn.folder_unreadable": "Não foi possível abrir esta pasta: {reason}",
        "warn.stage_unreadable": "Não foi possível abrir a pasta da etapa “{stage}”: {reason}",
        "warn.config_unreadable": "Não foi possível ler {name}: {reason}",
        "warn.multiple_configs": "Há {n} arquivos de configuração nesta pasta; usando “{used}”. Apague os outros.",
        "cfg.encoding": "{name} não está salvo como texto UTF-8, então os acentos podem sair errados. Salve de novo como UTF-8 ou use um Google Doc.",
        "cfg.duplicate_key": "“{key}:” aparece mais de uma vez em {name}; vale o último.",
        "cfg.key_in_description": "“{key}:” na linha {line} de {name} está abaixo do texto de descrição e é ignorado. Mova para junto dos outros campos.",
        "cfg.invalid_slug": "OCULTO PARA O CLIENTE: “Slug: {value}” não é um link válido. Use só letras minúsculas, números e hífens, sem espaços nem acentos (ex.: casa-nova-7k2p).",
        "warn.duplicate_folder_name": "{n} pastas de projeto se chamam “{name}”. Renomeie para diferenciá-las.",
        "warn.duplicate_stage": "Mais de uma etapa com o número {stage}: {names}. Renumere uma delas para a ordem da linha do tempo ficar clara.",
        "warn.duplicate_stage_name": "{n} pastas de etapa se chamam “{name}”. Renomeie ou numere.",
        "warn.stage_ambiguous": "“Etapa atual: {value}” corresponde a mais de uma etapa, então é ignorada e o status é calculado pelos arquivos. Renumere as etapas ou use o nome da etapa.",
        "err.not_found": "não encontrada ou não compartilhada com o site (um atalho para uma pasta fora da raiz compartilhada?)",
        "err.forbidden": "o site não tem permissão para ler",
        "err.other": "erro inesperado ({detail})",
        "dash.attention": "{n} de {total} projetos precisam de atenção",
        "dash.root_error": "Não foi possível ler a pasta raiz do Drive: {reason}",
        "dash.hidden": "Oculto",
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

# Extension → icon category (see the SVG symbols in templates/icons.html).
CATEGORIES = {
    "cad": {"dwg", "dxf", "dgn", "dwf", "dwfx"},
    "model": {"skp", "rvt", "rfa", "rte", "ifc", "3dm", "pln", "pla", "max", "blend", "obj", "fbx", "3ds", "dae", "stl", "nwd", "nwc"},
    "doc": {"pdf", "doc", "docx", "odt", "rtf", "txt", "md", "pages"},
    "sheet": {"xls", "xlsx", "xlsm", "csv", "ods", "numbers"},
    "slides": {"ppt", "pptx", "key", "odp"},
    "image": {"jpg", "jpeg", "png", "gif", "webp", "tif", "tiff", "heic", "bmp", "svg", "psd", "ai", "eps"},
    "video": {"mp4", "mov", "avi", "mkv", "webm", "m4v"},
    "archive": {"zip", "rar", "7z", "tar", "gz"},
}
NATIVE_CATEGORIES = {
    "application/vnd.google-apps.document": "doc",
    "application/vnd.google-apps.spreadsheet": "sheet",
    "application/vnd.google-apps.presentation": "slides",
    "application/vnd.google-apps.drawing": "image",
}


def lang() -> str:
    value = os.environ.get("SITE_LANG", "en").lower()
    return "pt" if value.startswith("pt") else "en"


def t(msg_id: str, /, **kwargs) -> str:
    text = STRINGS[lang()].get(msg_id) or STRINGS["en"].get(msg_id, msg_id)
    if isinstance(kwargs.get("reason"), str) and kwargs["reason"].startswith("err."):
        kwargs["reason"] = t(kwargs["reason"], detail=kwargs.get("detail", ""))
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text  # a message must never break the page


@lru_cache(maxsize=4)
def _zone(name: str):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def site_tz():
    return _zone(os.environ.get("SITE_TIMEZONE", "America/Sao_Paulo"))


def now() -> datetime:
    return datetime.now(timezone.utc)


def fmt_date(dt: datetime | None) -> str:
    if not dt:
        return ""
    local = dt.astimezone(site_tz())
    return f"{local.day} {MONTHS[lang()][local.month - 1]} {local.year}"


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


def extension(f: DriveFile) -> str:
    if "." in f.name:
        ext = f.name.rsplit(".", 1)[1]
        if 1 <= len(ext) <= 5 and ext.isalnum():
            return ext.lower()
    return ""


def type_label(f: DriveFile) -> str:
    if f.mime_type in NATIVE_LABELS:
        return NATIVE_LABELS[f.mime_type]
    return extension(f).upper() or "FILE"


def category(f: DriveFile) -> str:
    if f.mime_type.startswith(NATIVE_PREFIX):
        return NATIVE_CATEGORIES.get(f.mime_type, "file")
    ext = extension(f)
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    if f.mime_type.startswith("image/"):
        return "image"
    if f.mime_type.startswith("video/"):
        return "video"
    return "file"


def new_badge_days() -> int:
    try:
        return int(os.environ.get("NEW_BADGE_DAYS", "7"))
    except ValueError:
        return 7


def is_new(f: DriveFile) -> bool:
    days = new_badge_days()
    return bool(days > 0 and f.modified and f.modified >= now() - timedelta(days=days))
