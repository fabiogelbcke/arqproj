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
        "stage.expand": "Expand {stage}",
        "stage.collapse": "Collapse {stage}",
        "updates.heading": "Latest updates",
        "updates.unread": "{n} new updates",
        "updates.open": "View file",
        "updates.none": "Updates will appear here when files are available.",
        "stage.info": "About {stage}",
        "stage.about": "About this stage",
        "stage.delivery": "Expected deliverables",
        "stage.activities": "Activities developed",
        "stage.time": "Estimated time",
        "stage.fourteen_days": "14 days",
        "meeting.heading": "Meeting",
        "meeting.none": "No meeting scheduled",
        "meeting.default_title": "Project meeting · {project}",
        "file_search": "Search files",
        "file_search_empty": "No files found with that name.",
        "meeting.calendar": "Google Calendar",
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
        "stage.expand": "Expandir {stage}",
        "stage.collapse": "Recolher {stage}",
        "updates.heading": "Últimas atualizações",
        "updates.unread": "{n} novas atualizações",
        "updates.open": "Ver arquivo",
        "updates.none": "As atualizações aparecerão aqui quando houver arquivos disponíveis.",
        "stage.info": "Sobre {stage}",
        "stage.about": "Sobre esta etapa",
        "stage.delivery": "Entregas previstas",
        "stage.activities": "Etapas desenvolvidas",
        "stage.time": "Tempo estimado",
        "stage.fourteen_days": "14 dias",
        "meeting.heading": "Reunião",
        "meeting.none": "Não há reuniões agendadas",
        "meeting.default_title": "Reunião do projeto · {project}",
        "file_search": "Pesquisar arquivos",
        "file_search_empty": "Nenhum arquivo encontrado com esse nome.",
        "meeting.calendar": "Google Agenda",
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
    value = os.environ.get("SITE_LANG", "pt").lower()
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


# --- Drive connection panel (OAuth) ----------------------------------------
# Kept in one block, apart from the main table, so the whole feature can be
# removed in a single edit if the rewrite takes a different shape.
STRINGS["en"].update({
    "drive.title": "Google Drive connection",
    "drive.intro": "Connect the office's Google Drive. The files stay yours, in your "
                   "Drive — we only organise them and show them to your clients.",
    "drive.not_configured": "OAuth is not configured on this deployment "
                            "(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_REDIRECT_URI).",
    "drive.connect": "Connect Google Drive",
    "drive.connected": "Google Drive connected.",
    "drive.disconnect": "Disconnect",
    "drive.disconnected": "Disconnected.",
    "drive.denied": "Authorisation was cancelled.",
    "drive.bad_state": "That sign-in attempt expired. Please try again.",
    "drive.connect_failed": "Could not complete the connection: {detail}",
    "drive.failed": "That didn't work: {detail}",
    "drive.account": "Connected as",
    "drive.quota": "{used} of {total} used ({percent}%)",
    "drive.quota_unlimited": "Pooled storage (Workspace)",
    "drive.quota_warn": "Running low on space. We recommend a Google Workspace "
                        "account with a shared drive.",
    "drive.reconnect": "The connection to Google Drive has lapsed.",
    "drive.reconnect_body": "Client pages keep working — only creating new projects "
                            "needs the connection. Reconnect to continue.",
    "drive.delivery_folder": "Delivery folder",
    "drive.folder_default": "Portal Clientes",
    "drive.folder_name": "Folder name in your Drive",
    "drive.folder_create": "Create the delivery folder",
    "drive.folder_created": "Created “{name}” in your Drive.",
    "drive.folder_intro": "We create one folder for everything the client sees. "
                          "Your working files stay where they are.",
    "drive.shared_with": "Shared for reading with {email}",
    "drive.new_project": "New project",
    "drive.project_title": "Project name",
    "drive.project_slug": "Link (optional)",
    "drive.stages": "Stages",
    "drive.create": "Create project",
    "drive.project_created": "Created “{title}” as a draft.",
    "drive.need_title": "Give the project a name.",
    "drive.projects": "Projects created here",
    "drive.no_projects": "No projects yet.",
    "drive.draft": "Draft",
    "drive.publish": "Publish",
    "drive.published": "Published. It is now visible to clients.",
    "drive.open_drive": "Open in Drive",
    "drive.seen_by_sa": "Visible to the site",
    "drive.seen_intro": "What the site itself can read inside that folder. Drop a file "
                        "into it from Finder and it should appear here.",
    "drive.seen_none": "Nothing readable yet.",
    "drive.back": "Back to the dashboard",
    "drive.link": "Drive connection",
})
STRINGS["pt"].update({
    "drive.title": "Conexão com o Google Drive",
    "drive.intro": "Conecte o Google Drive do escritório. Os arquivos continuam sendo "
                   "seus, no seu Drive — nós só organizamos e mostramos para o cliente.",
    "drive.not_configured": "O OAuth não está configurado nesta instalação "
                            "(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_REDIRECT_URI).",
    "drive.connect": "Conectar o Google Drive",
    "drive.connected": "Google Drive conectado.",
    "drive.disconnect": "Desconectar",
    "drive.disconnected": "Desconectado.",
    "drive.denied": "A autorização foi cancelada.",
    "drive.bad_state": "A tentativa de login expirou. Tente novamente.",
    "drive.connect_failed": "Não foi possível concluir a conexão: {detail}",
    "drive.failed": "Não funcionou: {detail}",
    "drive.account": "Conectado como",
    "drive.quota": "{used} de {total} usados ({percent}%)",
    "drive.quota_unlimited": "Armazenamento compartilhado (Workspace)",
    "drive.quota_warn": "Pouco espaço livre. Recomendamos uma conta Google Workspace "
                        "com drive compartilhado.",
    "drive.reconnect": "A conexão com o Google Drive expirou.",
    "drive.reconnect_body": "As páginas dos clientes continuam funcionando — só a "
                            "criação de novos projetos depende da conexão. "
                            "Reconecte para continuar.",
    "drive.delivery_folder": "Pasta de entrega",
    "drive.folder_default": "Portal Clientes",
    "drive.folder_name": "Nome da pasta no seu Drive",
    "drive.folder_create": "Criar a pasta de entrega",
    "drive.folder_created": "Criamos “{name}” no seu Drive.",
    "drive.folder_intro": "Criamos uma pasta só para o que o cliente vê. Seus arquivos "
                          "de trabalho continuam onde estão.",
    "drive.shared_with": "Compartilhada para leitura com {email}",
    "drive.new_project": "Novo projeto",
    "drive.project_title": "Nome do projeto",
    "drive.project_slug": "Link (opcional)",
    "drive.stages": "Etapas",
    "drive.create": "Criar projeto",
    "drive.project_created": "“{title}” criado como rascunho.",
    "drive.need_title": "Dê um nome ao projeto.",
    "drive.projects": "Projetos criados aqui",
    "drive.no_projects": "Nenhum projeto ainda.",
    "drive.draft": "Rascunho",
    "drive.publish": "Publicar",
    "drive.published": "Publicado. Já está visível para os clientes.",
    "drive.open_drive": "Abrir no Drive",
    "drive.seen_by_sa": "Visível para o site",
    "drive.seen_intro": "O que o próprio site consegue ler dentro dessa pasta. Arraste "
                        "um arquivo para ela pelo Finder e ele deve aparecer aqui.",
    "drive.seen_none": "Nada legível ainda.",
    "drive.back": "Voltar ao painel",
    "drive.link": "Conexão com o Drive",
})
