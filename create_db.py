"""
create_db.py — Vytvorí SQLite databázu z CSV súborov.
Žiadne vymyslené dáta — všetko pochádza čisto z CSV.
"""
import sqlite3
import pandas as pd
import re
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'zdravdash.db')
CSV_DIR = os.environ.get('CSV_DIR', '/mnt/user-data/uploads')

def parse_gps_point(gps_str):
    """Parse 'POINT(49.xx 16.xx)' → (lat, lon)"""
    if pd.isna(gps_str):
        return None, None
    m = re.match(r'POINT\(([\d.]+)\s+([\d.]+)\)', str(gps_str))
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None

def parse_gps_plain(gps_str):
    """Parse '49.xx 16.xx' → (lat, lon)"""
    if pd.isna(gps_str) or not str(gps_str).strip():
        return None, None
    parts = str(gps_str).strip().split()
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None, None
    return None, None

def create_database():
    # Načítanie CSV
    print("Načítavam CSV súbory...")
    bigset = pd.read_csv(f'{CSV_DIR}/BigSetCZ064.csv', sep=';', encoding='utf-8-sig', dtype=str)
    data1 = pd.read_csv(f'{CSV_DIR}/DataKeStazeni1.csv', sep=';', encoding='utf-8-sig', dtype=str)
    data3 = pd.read_csv(f'{CSV_DIR}/DataKeStazeni3.csv', sep=';', encoding='utf-8-sig', dtype=str)

    print(f"  BigSet: {len(bigset)} riadkov")
    print(f"  Data1:  {len(data1)} riadkov")
    print(f"  Data3:  {len(data3)} riadkov")

    # GPS parsing pre Data1
    data1['lat'], data1['lon'] = zip(*data1['GPS'].apply(parse_gps_plain))

    # GPS parsing pre BigSet (pre lekárne)
    bigset['lat'], bigset['lon'] = zip(*bigset['ZZ_GPS'].apply(parse_gps_point))

    # Oddelenia lookup z Data3
    oddelenia_df = data3[['Ico', 'CisOddeleniKod']].dropna().drop_duplicates()

    # Vytvorenie DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ==================== SCHÉMA ====================

    cur.executescript("""
        CREATE TABLE zariadenia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ico TEXT,
            nazov TEXT,
            obec TEXT,
            psc TEXT,
            ulice TEXT,
            cislo TEXT,
            kraj TEXT,
            okres TEXT,
            lat REAL,
            lon REAL,
            obor_pece TEXT,
            druh_zarizeni TEXT,
            forma_pece TEXT,
            telefon TEXT,
            email TEXT,
            web TEXT,
            ruian_kod TEXT,
            datum_zahajeni TEXT,
            datova_schranka TEXT,
            je_lekarna INTEGER DEFAULT 0
        );

        CREATE TABLE oddelenia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ico TEXT,
            nazov_oddelenia TEXT
        );

        CREATE TABLE otvaracie_hodiny (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ico TEXT,
            ruian_kod TEXT,
            oddelenie TEXT,
            den TEXT,
            dopoledne TEXT,
            odpoledne TEXT
        );

        CREATE TABLE lekarne (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ico TEXT,
            nazov TEXT,
            obec TEXT,
            ulice TEXT,
            cislo TEXT,
            psc TEXT,
            lat REAL,
            lon REAL
        );

        CREATE INDEX idx_zariadenia_ico ON zariadenia(ico);
        CREATE INDEX idx_zariadenia_obor ON zariadenia(obor_pece);
        CREATE INDEX idx_zariadenia_obec ON zariadenia(obec);
        CREATE INDEX idx_zariadenia_lekarna ON zariadenia(je_lekarna);
        CREATE INDEX idx_zariadenia_lat_lon ON zariadenia(lat, lon);
        CREATE INDEX idx_oddelenia_ico ON oddelenia(ico);
        CREATE INDEX idx_hodiny_ico ON otvaracie_hodiny(ico);
        CREATE INDEX idx_hodiny_ruian ON otvaracie_hodiny(ico, ruian_kod);
        CREATE INDEX idx_lekarne_lat_lon ON lekarne(lat, lon);
    """)

    # ==================== ZARIADENIA z Data1 ====================
    print("Plním tabuľku zariadenia...")
    count = 0
    for _, row in data1.iterrows():
        druh = str(row.get('DruhZarizeni', '') or '')
        je_lekarna = 1 if 'Lékárna' in druh else 0

        cur.execute("""
            INSERT INTO zariadenia 
            (ico, nazov, obec, psc, ulice, cislo, kraj, okres, lat, lon,
             obor_pece, druh_zarizeni, forma_pece, telefon, email, web,
             ruian_kod, datum_zahajeni, datova_schranka, je_lekarna)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            str(row.get('Ico', '') or ''),
            str(row.get('NazevCely', '') or ''),
            str(row.get('Obec', '') or ''),
            str(row.get('Psc', '') or ''),
            str(row.get('Ulice', '') or ''),
            str(row.get('CisloDomovniOrientacni', '') or ''),
            str(row.get('Kraj', '') or ''),
            str(row.get('Okres', '') or ''),
            row['lat'],
            row['lon'],
            str(row.get('OborPece', '') or ''),
            druh,
            str(row.get('FormaPece', '') or ''),
            str(row.get('PoskytovatelTelefon', '') or ''),
            str(row.get('PoskytovatelEmail', '') or ''),
            str(row.get('PoskytovatelWeb', '') or ''),
            str(row.get('RUIANKod', '') or ''),
            str(row.get('DatumZahajeniCinnosti', '') or ''),
            str(row.get('IdentifikatorDatoveSchranky', '') or ''),
            je_lekarna
        ))
        count += 1
    print(f"  Vložených: {count}")

    # ==================== ODDELENIA z Data3 ====================
    print("Plním tabuľku oddelenia...")
    count = 0
    for _, row in oddelenia_df.iterrows():
        cur.execute("INSERT INTO oddelenia (ico, nazov_oddelenia) VALUES (?,?)",
                    (str(row['Ico']), str(row['CisOddeleniKod'])))
        count += 1
    print(f"  Vložených: {count}")

    # ==================== OTVÁRACIE HODINY z Data3 ====================
    print("Plním tabuľku otvaracie_hodiny...")
    count = 0
    for _, row in data3.iterrows():
        den = str(row.get('DenVTydnuKod', '') or '')
        if den not in ('Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'):
            continue
        cur.execute("""
            INSERT INTO otvaracie_hodiny (ico, ruian_kod, oddelenie, den, dopoledne, odpoledne)
            VALUES (?,?,?,?,?,?)
        """, (
            str(row.get('Ico', '') or ''),
            str(row.get('RUIANKod', '') or ''),
            str(row.get('CisOddeleniKod', '') or ''),
            den,
            str(row.get('Dopoledne', '') or ''),
            str(row.get('Odpoledne', '') or '')
        ))
        count += 1
    print(f"  Vložených: {count}")

    # ==================== LEKÁRNE z BigSet ====================
    print("Plním tabuľku lekarne...")
    pharm = bigset[bigset['ZZ_druh_nazev'].str.contains('Lékárna', na=False)].copy()
    pharm = pharm[pharm['lat'].notna()]
    pharm = pharm.drop_duplicates(subset=['poskytovatel_ICO', 'lat', 'lon'])
    count = 0
    for _, row in pharm.iterrows():
        cur.execute("""
            INSERT INTO lekarne (ico, nazov, obec, ulice, cislo, psc, lat, lon)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            str(row.get('poskytovatel_ICO', '') or ''),
            str(row.get('ZZ_nazev', '') or ''),
            str(row.get('ZZ_obec', '') or ''),
            str(row.get('ZZ_ulice', '') or ''),
            str(row.get('ZZ_cislo_domovni_orientacni', '') or ''),
            str(row.get('ZZ_PSC', '') or ''),
            float(row['lat']),
            float(row['lon'])
        ))
        count += 1
    print(f"  Vložených: {count}")

    conn.commit()

    # Štatistiky
    for table in ['zariadenia', 'oddelenia', 'otvaracie_hodiny', 'lekarne']:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]} záznamov")

    conn.close()
    print(f"\nDatabáza uložená: {DB_PATH}")
    print(f"Veľkosť: {os.path.getsize(DB_PATH) / 1024 / 1024:.1f} MB")


if __name__ == '__main__':
    create_database()
