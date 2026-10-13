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


def deliver(t, msg: EmailMessage) -> dict:
    """Open the tenant's SMTP connection and send. Raises MailError when nothing
    went out; returns {address: reason} for any recipient the server refused."""
    problems = smtp_problems(t)
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
