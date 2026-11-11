"""Outgoing mail through the organisation's own SMTP server.

The settings live on the tenant (Company Information -> Email and SMTP). The
browser never sees the password and cannot open an SMTP connection, so every
mail is built and sent here.

`deliver` is the only function that touches the network; tests replace it.
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

MAX_ATTACH_BYTES = 15 * 1024 * 1024     # most servers refuse more than 20-25 MB encoded


class MailError(Exception):
    """A configuration or delivery problem, with a message fit to show the user."""


def smtp_problems(t) -> list[str]:
    p = []
    if not t.smtp_from_email:
        p.append("send-from address is missing")
    if not t.smtp_host:
        p.append("SMTP host is missing")
    if not t.smtp_port:
        p.append("port is missing")
    if t.smtp_username and not t.smtp_password:
        p.append("password is missing")
    return p


def from_header(t) -> str:
    return formataddr((t.smtp_from_name or t.name or "", t.smtp_from_email or ""))


def build(t, *, to, cc=(), bcc=(), subject, body, attachments=()) -> EmailMessage:
    """attachments: iterable of (filename, bytes, mime type)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_header(t)
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if t.smtp_reply_to:
        msg["Reply-To"] = t.smtp_reply_to
    domain = (t.smtp_from_email or "localhost").split("@")[-1]
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(body or "")
    total = 0
    for name, data, mime in attachments:
        total += len(data)
        if total > MAX_ATTACH_BYTES:
            raise MailError("The attachments come to more than 15 MB; most mail servers "
                            "will refuse that. Send fewer or smaller files.")
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream",
                           filename=name)
    # Bcc is passed to the server as recipients only, never written into the headers
    msg._bcc = list(bcc)  # noqa: SLF001 - carried to deliver()
    return msg


def recipients(msg) -> list[str]:
    out = []
    for h in ("To", "Cc"):
        if msg[h]:
            out += [a.strip() for a in str(msg[h]).split(",") if a.strip()]
    out += getattr(msg, "_bcc", [])
    seen, uniq = set(), []
    for a in out:
        if a.lower() not in seen:
            seen.add(a.lower()); uniq.append(a)
    return uniq


def _deliver_graph(t, msg: EmailMessage):
    """Send message via modern Microsoft Graph API using Entra ID app credentials."""
    import base64
    import json
    import os
    import urllib.parse
    import urllib.request
    from email.utils import parseaddr

    tenant_id = os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("ENTRA_CLIENT_ID")
    client_secret = os.getenv("ENTRA_CLIENT_SECRET")

    if not (tenant_id and client_id and client_secret):
        return None

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }).encode("utf-8")

    try:
        req = urllib.request.Request(token_url, data=token_data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            token = json.loads(resp.read().decode("utf-8"))["access_token"]
    except Exception:
        return None

    def _recips(raw):
        res = []
        for a in raw:
            n, email = parseaddr(a.strip())
            if email:
                obj = {"address": email}
                if n:
                    obj["name"] = n
                res.append({"emailAddress": obj})
        return res

    to_raw = [a for a in str(msg.get("To", "")).split(",") if a.strip()]
    cc_raw = [a for a in str(msg.get("Cc", "")).split(",") if a.strip()]
    bcc_raw = getattr(msg, "_bcc", [])

    body_content = ""
    content_type = "Text"
    if msg.is_multipart():
        for part in msg.iter_parts():
            ct = part.get_content_type()
            if ct in ("text/plain", "text/html"):
                body_content = part.get_content()
                content_type = "HTML" if ct == "text/html" else "Text"
                break
    else:
        body_content = msg.get_content()

    attachments = []
    if msg.is_multipart():
        for part in msg.iter_attachments():
            fn = part.get_filename() or "attachment"
            payload = part.get_payload(decode=True)
            if payload:
                attachments.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": fn,
                    "contentType": part.get_content_type() or "application/octet-stream",
                    "contentBytes": base64.b64encode(payload).decode("utf-8")
                })

    graph_msg = {
        "message": {
            "subject": str(msg.get("Subject", "")),
            "body": {"contentType": content_type, "content": body_content},
            "toRecipients": _recips(to_raw),
            "ccRecipients": _recips(cc_raw),
            "bccRecipients": _recips(bcc_raw),
            "attachments": attachments
        },
        "saveToSentItems": "true"
    }
    if t.smtp_reply_to:
        n, em = parseaddr(t.smtp_reply_to)
        graph_msg["message"]["replyTo"] = [{"emailAddress": {"address": em or t.smtp_reply_to, "name": n or ""}}]

    from_addr = (t.smtp_from_email or "").strip() or "Alok.Jayant@aequmindia.in"

    send_url = f"https://graph.microsoft.com/v1.0/users/{from_addr}/sendMail"
    send_req = urllib.request.Request(
        send_url,
        data=json.dumps(graph_msg).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(send_req, timeout=30) as resp:
            return {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            err_msg = err_json.get("error", {}).get("message", err_body)
        except Exception:
            err_msg = err_body
        if "Mail.Send" in err_msg or "Access is denied" in err_msg or e.code == 403:
            raise MailError(
                "Microsoft Entra is connected, but the app needs the 'Mail.Send' Application Permission in Microsoft Entra ID (Azure Portal) with Admin Consent."
            )
        raise MailError(f"Microsoft 365 error ({e.code}): {err_msg}")


def deliver(t, msg: EmailMessage) -> dict:
    """Open the tenant's SMTP or Graph API connection and send. Raises MailError when
    nothing went out; returns {address: reason} for any recipient the server refused."""
    problems = smtp_problems(t)
    if (t.smtp_host or "").lower() in ("smtp.office365.com", "outlook.office365.com"):
        graph_res = _deliver_graph(t, msg)
        if graph_res is not None:
            return graph_res

    if problems:
        raise MailError("Mail is not set up: " + "; ".join(problems)
                        + ". Fill it in under Company Information → Email and SMTP.")
    enc = t.smtp_encryption or "STARTTLS"
    ctx = ssl.create_default_context()
    try:
        if enc == "SSL":
            smtp = smtplib.SMTP_SSL(t.smtp_host, t.smtp_port, timeout=30, context=ctx)
        else:
            smtp = smtplib.SMTP(t.smtp_host, t.smtp_port, timeout=30)
        try:
            smtp.ehlo()
            if enc == "STARTTLS":
                smtp.starttls(context=ctx)
                smtp.ehlo()
            if t.smtp_username:
                smtp.login(t.smtp_username, t.smtp_password or "")
            refused = smtp.send_message(msg, from_addr=t.smtp_from_email,
                                        to_addrs=recipients(msg))
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
    except smtplib.SMTPAuthenticationError:
        raise MailError("The SMTP server refused the username or password. For Gmail or "
                        "Microsoft 365 an app password is usually needed.")
    except smtplib.SMTPSenderRefused:
        raise MailError(f"The server will not send as {t.smtp_from_email}. Use the address "
                        "the SMTP account belongs to as the send-from address.")
    except smtplib.SMTPRecipientsRefused as e:
        raise MailError("The server refused every recipient: " + ", ".join(e.recipients))
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise MailError(f"Could not send through {t.smtp_host}:{t.smtp_port} "
                        f"({enc}): {e}")
    return {a: str(r) for a, r in (refused or {}).items()}
