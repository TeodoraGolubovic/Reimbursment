import streamlit as st
import pandas as pd
import os
import sqlite3
from PIL import Image
from PyPDF2 import PdfMerger
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import datetime

# Konfiguracija stranice
st.set_page_config(page_title="Zahtev za refundaciju", layout="wide")

# Konekcija sa SQLite bazom
DB_FILE = "troskovi.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS troskovi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ime TEXT,
            odobrio TEXT,
            kategorija TEXT,
            iznos REAL,
            valuta TEXT,
            fajlovi TEXT
        )
    ''')
    conn.commit()
    conn.close()

def reset_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM troskovi")  # Briše sve podatke iz tabele
    conn.commit()
    conn.close()
    st.session_state.troskovi = pd.DataFrame(columns=["Kategorija", "Ukupno Iznos", "Fajlovi"])
    st.session_state.app_started = True

init_db()

# Inicijalizacija sesije
if "app_started" not in st.session_state:
    st.session_state.app_started = False
if "troskovi" not in st.session_state:
    st.session_state.troskovi = pd.DataFrame(columns=["Kategorija", "Ukupno Iznos", "Fajlovi"])

# Dugme za pokretanje aplikacije
if st.button("Pokreni aplikaciju"):
    reset_db()
    st.success("Aplikacija je uspešno pokrenuta! Baza je resetovana.")

# Sakrivanje polja dok se aplikacija ne pokrene
if st.session_state.app_started:
    # Naslov aplikacije
    st.title("Zahtev za refundiranje troškova")
    
    # Unos podataka
    ime_prezime = st.text_input("Ime i prezime")
    odobrio = st.text_input("Osoba koja je odobrila", placeholder="Obavezno polje")
    
    kategorija = st.selectbox("Kategorija troška:", [
        "Prevoz, taxi (529111)",
        "Gorivo (51300)",
        "Putarine (53940)",
        "Reprezentacija, kurirska dostava (55100)",
        "Ostali troškovi - npr. parking, hotel (55900)"
    ])
    
    iznos_str = st.text_input("Iznos", value="", placeholder="Unesite iznos u RSD")
    
    try:
        iznos = float(iznos_str) if iznos_str.strip() else None  # None znači da korisnik mora uneti broj
    except ValueError:
        st.warning("Unesite validan broj za iznos.")
        iznos = None
    valuta = "RSD"
    
    # Upload jednog fajla
    uploaded_file = st.file_uploader("Otpremite račun", type=["pdf", "jpg", "png"], accept_multiple_files=False)
    
    # Dodavanje troška
    if st.button("Dodaj trošak"):
        if not odobrio or not uploaded_file:
            st.warning("Morate uneti osobu koja je odobrila i dodati račun.")
        else:
            file_path = os.path.join("uploads", uploaded_file.name)
            os.makedirs("uploads", exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(
                "INSERT INTO troskovi (ime, odobrio, kategorija, iznos, valuta, fajlovi) VALUES (?, ?, ?, ?, ?, ?)",
                (ime_prezime, odobrio, kategorija, iznos, valuta, file_path)
            )
            conn.commit()
            
            # Ponovno otvaranje konekcije kako bismo koristili je za čitanje
            df_conn = sqlite3.connect(DB_FILE)
            st.session_state.troskovi = pd.read_sql_query("SELECT kategorija, SUM(iznos) as ukupno_iznos, GROUP_CONCAT(fajlovi) as fajlovi FROM troskovi GROUP BY kategorija", df_conn)
            df_conn.close()
            conn.close()
            
            st.success("Trošak dodat!")
    
    # Prikaz tabele troškova
    df = st.session_state.troskovi
    st.dataframe(df)
else:
    st.warning("Kliknite na 'Pokreni aplikaciju' da biste započeli unos podataka.")

from hashlib import md5
from PIL import Image
from fpdf import FPDF
import os

# Dozvoliti učitavanje velikih slika
Image.MAX_IMAGE_PIXELS = None

# Funkcija za dobijanje hash vrednosti slike
def get_image_hash(image_path):
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB") 
            return md5(img.tobytes()).hexdigest()
    except:
        return None  # Ako postoji greska, preskoci sliku

if st.button("Preuzmi PDF"):
    if df.empty:
        st.warning("Nema podataka za izveštaj.")
    else:
        pdf_path = f"uploads/izvestaj_{datetime.date.today()}.pdf"

        # Kreiranje PDF-a sa troškovima
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 750, "ZAHTEV ZA REFUNDIRANJE TROŠKOVA")
        c.setFont("Helvetica", 12)
        c.drawString(50, 730, f"Podnosilac zahteva: {ime_prezime}")
        c.drawString(50, 710, f"Odobrio: {odobrio}")
        c.drawString(50, 690, f"Datum zahteva: {datetime.date.today()}")

        y = 660
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Sumirani troškovi po kategorijama:")
        y -= 20

        for _, row in df.iterrows():
            c.setFont("Helvetica", 11)
            c.drawString(50, y, f"{row['kategorija']}: {row['ukupno_iznos']} RSD")
            y -= 20

        ukupno = df["ukupno_iznos"].sum()
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, f"UKUPNO: {ukupno} RSD")

        c.save()

        # **Dodavanje slika i PDF računa u jedan PDF**
        merger = PdfMerger()
        merger.append(pdf_path)

        seen_hashes = set()  # Skup za praćenje hash vrednosti slika

        for _, row in df.iterrows():
            if row["fajlovi"]:
                for file_path in row["fajlovi"].split(","):
                    file_path = file_path.strip()

                    if file_path.endswith((".jpg", ".jpeg", ".png")):
                        try:
                            img_hash = get_image_hash(file_path)
                            if img_hash is None or img_hash in seen_hashes:
                                continue  # Preskačemo ako ne može da se otvori ili ako je duplikat

                            seen_hashes.add(img_hash)

                            img = Image.open(file_path).convert("RGB")

                            # **Prilagođavanje slike da zauzme celu A4 stranicu**
                            a4_width, a4_height = 210, 297  # A4 format u mm
                            img_width, img_height = img.size

                            # Izračunavanje odnosa stranica
                            img_ratio = img_width / img_height
                            a4_ratio = a4_width / a4_height

                            if img_ratio > a4_ratio:
                                
                                new_height = a4_height
                                new_width = a4_height * img_ratio
                            else:
                                
                                new_width = a4_width
                                new_height = a4_width / img_ratio

                            #čuvaj optimizovanu sliku
                            optimized_img_path = f"uploads/optimized_{os.path.basename(file_path)}.jpg"
                            img.save(optimized_img_path, "JPEG", quality=90)

                            # Konvertovanje slike u PDF i centriranje na A4 format
                            img_pdf_path = f"uploads/temp_{os.path.basename(file_path)}.pdf"
                            pdf = FPDF(unit="mm", format="A4")
                            pdf.add_page()

                            # Proračun za centriranje slike na stranici
                            x_offset = (a4_width - new_width) / 2
                            y_offset = (a4_height - new_height) / 2

                            pdf.image(optimized_img_path, x=x_offset, y=y_offset, w=new_width, h=new_height)
                            pdf.output(img_pdf_path, "F")

                            merger.append(img_pdf_path)

                        except:
                            continue  # Ako slika ne može da se učita, preskačemo

                    elif file_path.endswith(".pdf"):
                        merger.append(file_path)

        merger.write(pdf_path)
        merger.close()

        with open(pdf_path, "rb") as f:
            st.download_button("Preuzmi PDF izveštaj", f, file_name=f"izvestaj_{datetime.date.today()}.pdf")
