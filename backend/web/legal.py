"""Unio's privacy policy and terms of use (A33), for people and for Google's OAuth
consent screen.

    GET /privacidade   Política de Privacidade (with an English version)
    GET /termos        Termos de Uso (with an English version)

Unio's pages, not an office's: the same on every address, `myunio.app` included,
so they need no office (tenancy/middleware.py lets them through) and project
addresses can't take these names (RESERVED_SLUGS). Unio is run informally, with
no registered company; add the company's name and CNPJ here if that changes.
"""

from __future__ import annotations

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

PRODUCT = "Unio"
EMAIL = "arqdevproj@gmail.com"  # where privacy requests go
CITY = "Joinville/SC"  # foro: the city for legal disputes
UPDATED = "17 de outubro de 2026"
UPDATED_EN = "October 17, 2026"
GOOGLE_POLICY = "https://developers.google.com/terms/api-services-user-data-policy"
GOOGLE_PERMISSIONS = "https://myaccount.google.com/permissions"

_HEADERS = {
    "Cache-Control": "public, max-age=3600",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "X-Content-Type-Options": "nosniff",
}
_STYLE = (
    "body{font:16px/1.6 system-ui,sans-serif;max-width:42rem;margin:0 auto;padding:48px 16px 96px;"
    "color:#242629;background:#fff}h1{font-size:28px;line-height:1.2;margin:0 0 4px}"
    "h2{font-size:18px;margin:32px 0 8px}.date{color:#5c6066;margin:0 0 24px}"
    "nav{margin:0 0 32px;font-size:14px}nav a{margin-right:16px}"
    "hr{border:0;border-top:1px solid #d5d7d9;margin:56px 0 40px}a{color:inherit}"
    "@media(prefers-color-scheme:dark){body{color:#e8e9ea;background:#17181a}"
    ".date{color:#a3a7ad}hr{border-top-color:#3a3c40}}"
)

_MAIL = f'<a href="mailto:{EMAIL}">{EMAIL}</a>'
_LINK_GOOGLE_POLICY = (
    f'<a href="{GOOGLE_POLICY}">Política de Dados do Usuário dos Serviços de API do Google</a>'
)
_LINK_GOOGLE_POLICY_EN = f'<a href="{GOOGLE_POLICY}">Google API Services User Data Policy</a>'
_LINK_PERMISSIONS = f'<a href="{GOOGLE_PERMISSIONS}">myaccount.google.com/permissions</a>'

PRIVACY = f"""
<h1>Política de Privacidade</h1>
<p class="date">Última atualização: {UPDATED}</p>
<p>Esta política explica como o {PRODUCT} trata dados pessoais. O {PRODUCT} é uma plataforma
que escritórios de arquitetura usam para mostrar aos seus clientes as páginas dos projetos
(etapas, reuniões e arquivos) e para gerenciar essas páginas num painel.</p>

<h2>Quem é responsável</h2>
<p>O {PRODUCT} é operado de forma independente, ainda sem empresa registrada. Há dois papéis:</p>
<ul>
<li><strong>Cada escritório</strong> decide o que publica sobre os seus projetos e clientes e é o
controlador desses dados. O {PRODUCT} os trata em nome do escritório, apenas para prestar o
serviço. Pedidos sobre esses dados podem ser feitos ao escritório ou a nós, e nós os
encaminhamos.</li>
<li><strong>O {PRODUCT}</strong> é o controlador dos dados das contas da equipe dos escritórios,
dos registros técnicos e do acesso ao Google descrito abaixo.</li>
</ul>
<p>Para qualquer assunto de privacidade, escreva para {_MAIL}.</p>

<h2>Quais dados tratamos</h2>
<ul>
<li><strong>Clientes e visitantes das páginas de projeto:</strong> o conteúdo que o escritório
publica sobre o projeto (por exemplo, o nome do cliente, descrições, datas de reunião e
arquivos) e os endereços de e-mail que o escritório cadastra para receber atualizações.</li>
<li><strong>Equipe dos escritórios:</strong> nome, e-mail, senha (guardada apenas de forma
cifrada) e, se uma conta Google for conectada, o acesso descrito abaixo.</li>
<li><strong>Registros técnicos:</strong> endereço IP, navegador, data e hora das solicitações,
usados para segurança e para corrigir problemas, guardados por até 30 dias.</li>
<li><strong>Cookies:</strong> apenas os estritamente necessários (manter a equipe conectada e
lembrar uma senha de projeto já digitada). Não usamos cookies de publicidade nem de análise.
A preferência de tema claro ou escuro e as atualizações já lidas ficam só no seu navegador.</li>
</ul>

<h2>E-mails de atualização</h2>
<p>Quando o escritório cadastra o e-mail de um cliente, o {PRODUCT} envia avisos sobre o projeto
(novos arquivos, mudanças de etapa e reuniões), agrupados para não enviar um e-mail a cada
mudança. Cada e-mail tem um link para deixar de recebê-los; depois disso, aquele endereço não
recebe mais nada do projeto.</p>

<h2>Dados do Google</h2>
<p>A equipe de um escritório pode conectar uma conta Google ao {PRODUCT}. O {PRODUCT} pede apenas
a permissão <code>drive.file</code>, que dá acesso somente aos arquivos e pastas que o próprio
{PRODUCT} cria ou que a pessoa abre com ele, e não ao restante do Google Drive. Esse acesso é
usado exclusivamente para criar as pastas dos projetos, enviar arquivos e mostrá-los aos
clientes do escritório. Os arquivos continuam no Google Drive do escritório.</p>
<p>Não vendemos esses dados, não os usamos para publicidade e não os compartilhamos, exceto
quando necessário para prestar o serviço, para cumprir a lei ou para proteger a segurança do
serviço. Ninguém lê esse conteúdo, exceto com consentimento de quem o enviou, para investigar
um problema de segurança ou por obrigação legal.</p>
<p>O uso e a transferência, para qualquer outro aplicativo, de informações recebidas das APIs do
Google seguem a {_LINK_GOOGLE_POLICY}, incluindo os requisitos de Uso Limitado.</p>
<p>O acesso pode ser revogado a qualquer momento no próprio painel ou em {_LINK_PERMISSIONS}.</p>

<h2>Com quem compartilhamos</h2>
<p>O {PRODUCT} funciona na infraestrutura do Google Cloud (servidores nos Estados Unidos), e os
arquivos ficam no Google Drive de cada escritório. Os e-mails de atualização são enviados pela
Resend, que recebe apenas o necessário para a entrega. Esses provedores tratam os dados por
nossa conta, sob contrato. A transferência internacional segue a Lei Geral de Proteção de Dados
(LGPD). Os dados de um escritório nunca são mostrados a outro escritório.</p>

<h2>Por quanto tempo</h2>
<p>Mantemos os dados enquanto o projeto ou a conta estiverem ativos, e depois pelo tempo exigido
por lei ou necessário para exercer direitos. Registros técnicos são apagados em até 30 dias.</p>

<h2>Seus direitos</h2>
<p>Pela LGPD, você pode pedir a confirmação de que tratamos seus dados, acesso, correção,
anonimização, bloqueio ou eliminação, portabilidade, informação sobre com quem compartilhamos e
a revogação de consentimento. Escreva para {_MAIL}; responderemos em até 15 dias. Você também
pode reclamar à Autoridade Nacional de Proteção de Dados (ANPD).</p>

<h2>Segurança</h2>
<p>Usamos conexões cifradas (HTTPS), senhas guardadas apenas de forma cifrada, separação dos dados
de cada escritório no banco de dados e registros de segurança.</p>

<h2>Mudanças</h2>
<p>Se esta política mudar, a nova versão será publicada nesta página com a data de
atualização.</p>

<hr>

<h1 lang="en">Privacy Policy</h1>
<div lang="en">
<p class="date">Last updated: {UPDATED_EN}. The Portuguese version above prevails.</p>
<p>This policy explains how {PRODUCT} handles personal data. {PRODUCT} is a platform that
architecture offices use to show their clients pages about their projects (stages, meetings and
files) and to manage those pages from a dashboard.</p>

<h2>Who is responsible</h2>
<p>{PRODUCT} is run independently, without a registered company yet. There are two roles:</p>
<ul>
<li><strong>Each office</strong> decides what it publishes about its projects and clients and is
the controller of that data. {PRODUCT} processes it on the office's behalf, only to provide the
service. Requests about that data can go to the office or to us, and we pass them on.</li>
<li><strong>{PRODUCT}</strong> is the controller of office staff accounts, technical logs, and
the Google access described below.</li>
</ul>
<p>For any privacy matter, write to {_MAIL}.</p>

<h2>What we process</h2>
<ul>
<li><strong>Clients and visitors of project pages:</strong> what the office publishes about the
project (such as the client's name, descriptions, meeting dates and files) and the email
addresses the office adds to receive updates.</li>
<li><strong>Office staff:</strong> name, email, password (stored only in hashed form) and, if a
Google account is connected, the access described below.</li>
<li><strong>Technical logs:</strong> IP address, browser, and time of requests, for security and
troubleshooting, kept for up to 30 days.</li>
<li><strong>Cookies:</strong> only strictly necessary ones (keeping staff signed in and
remembering a project password already entered). No advertising or analytics cookies. The light
or dark theme choice and which updates were read stay in your browser.</li>
</ul>

<h2>Update emails</h2>
<p>When an office adds a client's email address, {PRODUCT} sends notices about the project (new
files, stage changes and meetings), grouped so that not every change sends an email. Every email
has a link to stop receiving them; after that, the address gets nothing more from that
project.</p>

<h2>Google user data</h2>
<p>An office's staff may connect a Google account to {PRODUCT}. {PRODUCT} requests only the
<code>drive.file</code> permission, which covers only files and folders {PRODUCT} itself creates
or that the person opens with it, not the rest of their Google Drive. This access is used solely
to create project folders, upload files, and show them to the office's clients. Files stay in the
office's Google Drive.</p>
<p>We do not sell this data, use it for advertising, or share it except as needed to provide the
service, to comply with law, or to protect the service's security. No one reads this content
except with the consent of whoever uploaded it, to investigate a security issue, or where the law
requires.</p>
<p>{PRODUCT}'s use and transfer to any other app of information received from Google APIs will
adhere to the {_LINK_GOOGLE_POLICY_EN}, including the Limited Use requirements.</p>
<p>Access can be revoked at any time in the dashboard or at {_LINK_PERMISSIONS}.</p>

<h2>Sharing</h2>
<p>{PRODUCT} runs on Google Cloud (servers in the United States), and files are kept in each
office's Google Drive. Update emails are sent through Resend, which receives only what delivery
requires. These providers process data on our behalf under contract. International transfers
follow Brazil's General Data Protection Law (LGPD). One office's data is never shown to another
office.</p>

<h2>Retention</h2>
<p>We keep data while the project or account is active, then for as long as the law requires or
as needed to exercise legal rights. Technical logs are deleted within 30 days.</p>

<h2>Your rights</h2>
<p>Under the LGPD you may ask for confirmation of processing, access, correction, anonymization,
blocking or deletion, portability, information about sharing, and withdrawal of consent. Write to
{_MAIL}; we answer within 15 days. You may also complain to Brazil's data protection authority
(ANPD).</p>

<h2>Security</h2>
<p>We use encrypted connections (HTTPS), passwords stored only in hashed form, separation of each
office's data in the database, and security logs.</p>

<h2>Changes</h2>
<p>If this policy changes, the new version will be published on this page with its date.</p>
</div>
"""

TERMS = f"""
<h1>Termos de Uso</h1>
<p class="date">Última atualização: {UPDATED}</p>

<h2>O serviço</h2>
<p>O {PRODUCT} permite que escritórios de arquitetura compartilhem com seus clientes o andamento
dos projetos, reuniões e arquivos, e que a equipe de cada escritório gerencie esse conteúdo. O
{PRODUCT} é operado de forma independente, ainda sem empresa registrada. Ao usar o {PRODUCT},
você concorda com estes termos e com a <a href="/privacidade">Política de Privacidade</a>.</p>

<h2>Acesso</h2>
<p>As páginas de projeto são destinadas ao cliente do projeto e a quem ele escolher. Trate o
endereço e a senha de um projeto como informação confidencial. O painel é de uso exclusivo da
equipe do escritório; cada pessoa é responsável pela própria senha e pelo que faz com a sua
conta.</p>

<h2>Conteúdo</h2>
<p>Os desenhos, documentos e demais conteúdos dos projetos pertencem ao escritório ou ao cliente,
conforme o contrato entre eles. O escritório é responsável pelo que publica e por ter o direito
de publicá-lo. O {PRODUCT} apenas apresenta esse conteúdo; os arquivos continuam no Google Drive
do escritório.</p>

<h2>Uso adequado</h2>
<p>Não é permitido tentar acessar projetos, contas ou dados de outros escritórios ou de terceiros,
interferir no funcionamento do {PRODUCT}, nem usá-lo para fins ilegais.</p>

<h2>Disponibilidade e responsabilidade</h2>
<p>Trabalhamos para manter o {PRODUCT} disponível e correto, mas ele pode passar por
interrupções. As informações oficiais de cada projeto são as acordadas entre o escritório e o
cliente. Na medida permitida pela lei, não respondemos por danos indiretos decorrentes do uso do
{PRODUCT}.</p>

<h2>Mudanças</h2>
<p>Estes termos podem ser atualizados; a nova versão será publicada nesta página com a data.</p>

<h2>Lei e foro</h2>
<p>Aplica-se a lei brasileira. Fica eleito o foro de {CITY}, salvo disposição legal em
contrário, como os direitos do consumidor. Contato: {_MAIL}.</p>

<hr>

<h1 lang="en">Terms of Use</h1>
<div lang="en">
<p class="date">Last updated: {UPDATED_EN}. The Portuguese version above prevails.</p>

<h2>The service</h2>
<p>{PRODUCT} lets architecture offices share with their clients how projects, meetings and files
are progressing, and lets each office's staff manage that content. {PRODUCT} is run
independently, without a registered company yet. By using {PRODUCT} you agree to these terms
and to the <a href="/privacidade">Privacy Policy</a>.</p>

<h2>Access</h2>
<p>Project pages are meant for the project's client and whoever they choose. Treat a project's
address and password as confidential. The dashboard is for the office's staff only; each person
is responsible for their own password and for what is done with their account.</p>

<h2>Content</h2>
<p>Drawings, documents and other project content belong to the office or the client, as their
contract says. The office is responsible for what it publishes and for having the right to
publish it. {PRODUCT} only presents that content; files stay in the office's Google Drive.</p>

<h2>Acceptable use</h2>
<p>Do not try to access other offices' or third parties' projects, accounts or data, interfere
with {PRODUCT}, or use it for unlawful purposes.</p>

<h2>Availability and liability</h2>
<p>We work to keep {PRODUCT} available and accurate, but it may be interrupted. The official
information about each project is what the office and the client have agreed. To the extent the
law allows, we are not liable for indirect damages arising from the use of {PRODUCT}.</p>

<h2>Changes</h2>
<p>These terms may be updated; the new version will be published on this page with its date.</p>

<h2>Law and venue</h2>
<p>Brazilian law applies. The courts of {CITY} have jurisdiction, unless the law provides
otherwise, as with consumer rights. Contact: {_MAIL}.</p>
</div>
"""


def _page(title: str, body: str) -> HTMLResponse:
    nav = (
        '<nav><a href="/privacidade">Política de Privacidade</a>'
        '<a href="/termos">Termos de Uso</a></nav>'
    )
    return HTMLResponse(
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)} · {PRODUCT}</title><style>{_STYLE}</style>"
        f"<body>{nav}{body}</body></html>",
        headers=_HEADERS,
    )


@router.get("/privacidade")
def privacy() -> HTMLResponse:
    return _page("Política de Privacidade", PRIVACY)


@router.get("/termos")
def terms() -> HTMLResponse:
    return _page("Termos de Uso", TERMS)
