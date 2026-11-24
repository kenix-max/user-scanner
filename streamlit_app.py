import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="User Scanner", page_icon="🔎", layout="wide")
st.title("🔎 User Scanner")
st.caption("Digital Footprint Scanner")

with st.form("scan_form"):
    mode = st.radio("Tip pretrage", ["Username", "Email"], horizontal=True)
    target = st.text_input("Unesi korisničko ime ili e-mail", max_chars=254)
    consent = st.checkbox("Proveravam svoje naloge ili imam dozvolu za proveru.")
    submitted = st.form_submit_button("Pokreni pretragu", type="primary", use_container_width=True)

if submitted:
    st.session_state.pop("scan_results", None)
    target = target.strip()
    if not consent:
        st.warning("Potvrdi da imaš dozvolu za proveru.")
    elif not target or not re.fullmatch(r"[^\s*?\[\]\x00-\x1f\x7f]+", target):
        st.warning("Unesi jednu vrednost, bez razmaka ili wildcard znakova.")
    elif mode == "Email" and not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", target):
        st.warning("Unesi ispravnu e-mail adresu.")
    else:
        try:
            with st.spinner("Pretraga je u toku..."):
                with tempfile.TemporaryDirectory() as tmp:
                    report = Path(tmp) / "results.json"
                    flag = "--email" if mode == "Email" else "--username"
                    command = [
                        sys.executable, "-m", "user_scanner",
                        f"{flag}={target}", "--no-nsfw",
                        "--format", "json", "--output", str(report),
                    ]
                    result = subprocess.run(
                        command, cwd=ROOT, stdin=subprocess.DEVNULL,
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=600, check=False,
                    )
                    if result.returncode != 0 or not report.is_file():
                        st.error("Skener nije napravio ispravan izveštaj.")
                        with st.expander("Tehnički detalji"):
                            st.code((result.stderr or result.stdout)[-5000:])
                    else:
                        data = json.loads(report.read_text(encoding="utf-8"))
                        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
                            raise ValueError("Neočekivan format izveštaja")
                        st.session_state["scan_results"] = data
        except subprocess.TimeoutExpired:
            st.error("Pretraga je prekinuta nakon 10 minuta.")
        except (OSError, ValueError) as exc:
            st.error(f"Greška: {exc}")

if "scan_results" in st.session_state:
    data = st.session_state["scan_results"]
    found = [r for r in data if r.get("status") in ("Found", "Registered")]
    errors = sum(r.get("status") == "Error" for r in data)
    skipped = sum(r.get("status") == "Skipped" for r in data)
    a, b, c, d = st.columns(4)
    a.metric("Provereno", len(data))
    b.metric("Pronađeno", len(found))
    c.metric("Greške", errors)
    d.metric("Preskočeno", skipped)
    show_all = st.checkbox("Prikaži sve rezultate")
    rows = data if show_all else found
    if rows:
        df = pd.DataFrame(rows).reindex(columns=["site_name", "category", "status", "url", "reason"])
        df["url"] = df["url"].map(lambda u: u if isinstance(u, str) and u.lower().startswith(("https://", "http://")) else None)
        st.dataframe(df, hide_index=True, use_container_width=True,
            column_config={
                "site_name": "Platforma", "category": "Kategorija",
                "status": "Status", "url": st.column_config.LinkColumn("Link"),
                "reason": "Detalji",
            })
    else:
        st.info("Nema pronađenih naloga za prikaz. Proveri i greške i preskočene platforme.")
    st.download_button("Sačuvaj JSON izveštaj (svi rezultati)",
        data=json.dumps(data, ensure_ascii=False, indent=2),
        file_name="results.json", mime="application/json")
    st.caption("Poklapanje nije dokaz identiteta ili vlasništva nad nalogom.")
