import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import bcrypt
import boto3
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
ROOT = Path(__file__).parent
LOCAL_FILES = ROOT / "uploads"
LOCAL_DATA = ROOT / "data" / "shares.json"
MAX_BYTES = 20 * 1024 * 1024
MAX_HOURS = 168
st.set_page_config(page_title="VaultLink — Secure File Sharing", page_icon="🔐", layout="centered")

@st.cache_resource
def mongo_collection(uri, database):
    client = MongoClient(uri, serverSelectionTimeoutMS=4000, tz_aware=True)
    client.admin.command("ping")
    collection = client[database]["shares"]
    collection.create_index("token_hash", unique=True)
    collection.create_index("expires_at", expireAfterSeconds=0)
    return collection

def cloud_config():
    return {
        "bucket": os.getenv("S3_BUCKET", "").strip(),
        "region": os.getenv("AWS_REGION", "ap-south-1"),
        "mongo_uri": os.getenv("MONGODB_URI", "").strip(),
        "mongo_db": os.getenv("MONGODB_DB", "secure_file_sharing"),
    }

def get_collection():
    cfg = cloud_config()
    if not cfg["mongo_uri"]:
        return None
    return mongo_collection(cfg["mongo_uri"], cfg["mongo_db"])

def read_local():
    LOCAL_DATA.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILES.mkdir(parents=True, exist_ok=True)
    if not LOCAL_DATA.exists():
        LOCAL_DATA.write_text("[]", encoding="utf-8")
    records = json.loads(LOCAL_DATA.read_text(encoding="utf-8"))
    for record in records:
        for field in ("created_at", "expires_at"):
            if isinstance(record.get(field), str):
                value = datetime.fromisoformat(record[field])
                record[field] = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return records

def find_share(token_hash):
    collection = get_collection()
    if collection is not None:
        return collection.find_one({"token_hash": token_hash})
    return next((record for record in read_local() if record["token_hash"] == token_hash), None)

def save_share(share):
    collection = get_collection()
    if collection is not None:
        collection.insert_one(share)
    else:
        records = read_local()
        stored = dict(share)
        stored["created_at"] = share["created_at"].isoformat()
        stored["expires_at"] = share["expires_at"].isoformat()
        records.append(stored)
        LOCAL_DATA.write_text(json.dumps(records, indent=2), encoding="utf-8")

def expired(share):
    return share is None or share["expires_at"].timestamp() <= datetime.now(timezone.utc).timestamp()

def store_file(object_key, file_bytes, content_type):
    cfg = cloud_config()
    if cfg["bucket"]:
        boto3.client("s3", region_name=cfg["region"]).put_object(
            Bucket=cfg["bucket"], Key=object_key, Body=file_bytes,
            ContentType=content_type or "application/octet-stream",
            ServerSideEncryption="AES256",
        )
    else:
        LOCAL_FILES.mkdir(parents=True, exist_ok=True)
        (LOCAL_FILES / object_key).write_bytes(file_bytes)

def get_local_file(object_key):
    return (LOCAL_FILES / object_key).read_bytes()

def download_url(share):
    cfg = cloud_config()
    remaining = int((share["expires_at"] - datetime.now(timezone.utc)).total_seconds())
    return boto3.client("s3", region_name=cfg["region"]).generate_presigned_url(
        "get_object",
        Params={
            "Bucket": cfg["bucket"], "Key": share["object_key"],
            "ResponseContentDisposition": f'attachment; filename="{quote(share["file_name"], safe="")}"',
        },
        ExpiresIn=max(1, min(600, remaining)),
    )

def relative_time(value):
    return value.astimezone().strftime("%d %b %Y, %I:%M %p")

def render_share_page(token):
    st.markdown("### 🔐 Secure download")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        share = find_share(token_hash)
    except Exception:
        st.error("Could not connect to the configured metadata database.")
        return
    if expired(share):
        st.error("This share link has expired or does not exist.")
        return
    st.subheader(share["file_name"])
    st.caption(f"{share['size'] / (1024 * 1024):.2f} MB · Link expires {relative_time(share['expires_at'])}")
    password = ""
    if share.get("password_hash"):
        password = st.text_input("Download password", type="password", key="share_password")
    if st.button("Continue to download", type="primary"):
        if share.get("password_hash"):
            try:
                if not bcrypt.checkpw(password.encode(), share["password_hash"].encode()):
                    st.error("That password is incorrect.")
                    return
            except ValueError:
                st.error("That password could not be checked.")
                return
        if expired(share):
            st.error("This share link has expired.")
            return
        try:
            if cloud_config()["bucket"]:
                st.link_button("Download file", download_url(share), type="primary")
                st.caption("The download link is temporary and expires within 10 minutes.")
            else:
                content = get_local_file(share["object_key"])
                st.download_button(
                    "Download file", content, file_name=share["file_name"],
                    mime=share.get("content_type") or "application/octet-stream",
                    type="primary",
                )
        except Exception:
            st.error("The file could not be retrieved. Check the storage configuration.")

def render_upload_page():
    st.markdown("## Your files. Your rules.")
    st.write("Upload a file and create a private link that expires when you choose.")
    with st.container(border=True):
        st.markdown("### Create a share link")
        owner_password = st.text_input("Workspace password", type="password", help="Set with UPLOAD_PASSWORD in the .env file.")
        uploaded = st.file_uploader("Choose a file (maximum 20 MB)", max_upload_size=20)
        expiry = st.selectbox("Link expires after", [("1 hour", 1), ("6 hours", 6), ("24 hours", 24), ("3 days", 72), ("7 days", 168)], index=2, format_func=lambda choice: choice[0])
        protect = st.checkbox("Add a password for the recipient")
        link_password = st.text_input("Recipient password", type="password", max_chars=72) if protect else ""
        if st.button("Create secure link", type="primary", use_container_width=True):
            configured_password = os.getenv("UPLOAD_PASSWORD", "")
            if not configured_password:
                st.error("Set UPLOAD_PASSWORD in your .env file first, then restart Streamlit.")
            elif not secrets.compare_digest(owner_password, configured_password):
                st.error("Workspace password is incorrect.")
            elif uploaded is None:
                st.error("Choose a file first.")
            elif uploaded.size > MAX_BYTES:
                st.error("Files must be 20 MB or smaller.")
            elif protect and not link_password:
                st.error("Enter a recipient password or turn off password protection.")
            else:
                try:
                    token = secrets.token_urlsafe(32)
                    object_key = secrets.token_hex(16)
                    now = datetime.now(timezone.utc)
                    expires_at = now + timedelta(hours=expiry[1])
                    password_hash = bcrypt.hashpw(link_password.encode(), bcrypt.gensalt()).decode() if protect else None
                    store_file(object_key, uploaded.getvalue(), uploaded.type)
                    share = {
                        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                        "object_key": object_key,
                        "file_name": Path(uploaded.name.replace("\\", "/")).name[:180],
                        "content_type": uploaded.type or "application/octet-stream",
                        "size": uploaded.size,
                        "created_at": now,
                        "expires_at": expires_at,
                        "password_hash": password_hash,
                    }
                    save_share(share)
                    base_url = os.getenv("APP_BASE_URL", "http://localhost:8501").rstrip("/")
                    st.session_state["created_link"] = f"{base_url}/?token={token}"
                    st.session_state["created_expiry"] = expires_at
                    st.rerun()
                except Exception:
                    st.error("Could not create the link. Check your AWS and MongoDB settings, then try again.")
    if st.session_state.get("created_link"):
        st.success("Your secure link is ready.")
        st.code(st.session_state["created_link"], language=None)
        st.caption(f"Expires {relative_time(st.session_state['created_expiry'])}. Share the link only with its intended recipient.")
        st.button("Create another link", on_click=lambda: st.session_state.pop("created_link", None))

def main():
    st.markdown(
        """<style>
        .stApp {background: #f4f7fb}
        .block-container {max-width: 760px;padding-top:2.5rem}
        h1,h2,h3 {color:#102a43}
        [data-testid="stMetric"] {background:white;border:1px solid #e5eaf0;border-radius:12px;padding:14px}
        </style>""",
        unsafe_allow_html=True,
    )
    st.markdown("### 🔐 VaultLink")
    st.caption("PRIVATE FILE SHARING · CLOUD COMPUTING MINI PROJECT")
    token = st.query_params.get("token")
    if token:
        render_share_page(token)
    else:
        render_upload_page()
    st.divider()
    cfg = cloud_config()
    st.caption(
        f"File storage: {'AWS S3' if cfg['bucket'] else 'local demo'} · "
        f"Metadata: {'MongoDB' if cfg['mongo_uri'] else 'local demo'}"
    )
    st.caption("Educational prototype. Do not use for sensitive files without adding user accounts and production safeguards.")

main()


