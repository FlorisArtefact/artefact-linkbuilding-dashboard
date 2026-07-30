"""
Shared Google service-account credential resolution.
Used by sheets_loader, gsc_client and ga4_client so all three
read credentials the same way: Streamlit Cloud secrets first,
falling back to a local JSON file for local development.
"""
import os


def get_credentials(creds_file: str, scopes: list):
    from google.oauth2 import service_account
    import streamlit as st

    try:
        if "gcp_service_account" in st.secrets:
            return service_account.Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]), scopes=scopes
            )
    except Exception:
        pass

    return service_account.Credentials.from_service_account_file(creds_file, scopes=scopes)


def credentials_configured(creds_file: str) -> bool:
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            return True
    except Exception:
        pass
    return bool(creds_file) and os.path.exists(creds_file)
