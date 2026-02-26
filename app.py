"""
app.py — Flask backend pre ZdravDash.
Všetky dáta pochádzajú z SQLite databázy (naplnenej z CSV).
"""
import sqlite3
import os
from math import radians, cos, sin, asin, sqrt
from flask import Flask, render_template, request, jsonify

app = Flask(__name__, template_folder=os.path.dirname(__file__))
DB_PATH = os.path.join(os.path.dirname(__file__), 'zdravdash.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def normalize(text):
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()


def clean_field(value):
    """Vráti hodnotu alebo None ak je prázdna/nan."""
    if not value or str(value).strip() in ('', 'nan', 'None', 'none'):
        return None
    return str(value).strip()


def format_hodiny(dop, odp):
    """
    Formátovanie ordinačných hodín z DB.
    - Ak sú obe 'x' alebo prázdne → None (= NEDOSTUPNÉ)
    - Ak sú reálne časy → vráti formátovaný string
    - Ak zavřeno → 'zavřeno'
    """
    dop = (dop or '').strip()
    odp = (odp or '').strip()

    if dop.lower() in ('zavřeno', 'neordinuje', 'neordinujeme'):
        if not odp or odp == 'x':
            return 'zavřeno'

    has_dop_time = dop and dop != 'x' and any(c.isdigit() for c in dop)
    has_odp_time = odp and odp != 'x' and any(c.isdigit() for c in odp)

    if has_dop_time and has_odp_time:
        return f"{dop} | {odp}"
    elif has_dop_time:
        return dop
    elif dop.lower() == 'dle objednání' or odp.lower() == 'dle objednání':
        return 'dle objednání'
    elif dop == 'x' and odp == 'x':
        return None
    elif dop == 'x' or odp == 'x':
        return None
    elif dop:
        return dop

    return None


def build_address(ulice, cislo, psc, obec):
    """Zostaví adresu z komponentov."""
    ulice = clean_field(ulice)
    cislo = clean_field(cislo)
    psc = clean_field(psc)
    obec = clean_field(obec)

    parts = []
    if ulice and cislo:
        parts.append(f"{ulice} {cislo}")
    elif ulice:
        parts.append(ulice)
    elif cislo:
        parts.append(cislo)

    if psc and obec:
        parts.append(f"{psc} {obec}")
    elif obec:
        parts.append(obec)
    elif psc:
        parts.append(psc)

    return ', '.join(parts) if parts else None


# ==================== API ENDPOINTS ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    page = int(request.args.get('page', 0))
    limit = int(request.args.get('limit', 50))
    offset = page * limit

    db = get_db()

    if not q:
        rows = db.execute("""
            SELECT * FROM zariadenia 
            WHERE je_lekarna = 0 AND lat IS NOT NULL
            ORDER BY nazov
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        total = db.execute(
            "SELECT COUNT(*) FROM zariadenia WHERE je_lekarna = 0 AND lat IS NOT NULL"
        ).fetchone()[0]
    else:
        q_norm = normalize(q)
        terms = q_norm.split()

        matching_icos_odd = set()
        all_odd = db.execute("SELECT ico, nazov_oddelenia FROM oddelenia").fetchall()
        for row in all_odd:
            if all(t in normalize(row['nazov_oddelenia']) for t in terms):
                matching_icos_odd.add(row['ico'])

        all_zar = db.execute("""
            SELECT id, ico, nazov, obec, obor_pece, druh_zarizeni
            FROM zariadenia 
            WHERE je_lekarna = 0 AND lat IS NOT NULL
        """).fetchall()

        matching_ids = []
        for row in all_zar:
            searchable = normalize(' '.join([
                row['nazov'] or '',
                row['obec'] or '',
                row['obor_pece'] or '',
                row['druh_zarizeni'] or '',
                row['ico'] or ''
            ]))
            from_oddelenie = row['ico'] in matching_icos_odd
            if from_oddelenie or all(t in searchable for t in terms):
                matching_ids.append(row['id'])

        total = len(matching_ids)

        if matching_ids:
            page_ids = matching_ids[offset:offset + limit]
            placeholders = ','.join('?' * len(page_ids))
            rows = db.execute(
                f"SELECT * FROM zariadenia WHERE id IN ({placeholders}) ORDER BY nazov",
                page_ids
            ).fetchall()
        else:
            rows = []

    results = []
    for row in rows:
        oddelenia = db.execute(
            "SELECT DISTINCT nazov_oddelenia FROM oddelenia WHERE ico = ?",
            (row['ico'],)
        ).fetchall()

        results.append({
            'id': row['id'],
            'ico': clean_field(row['ico']) or '-',
            'nazov': clean_field(row['nazov']) or '-',
            'adresa': build_address(row['ulice'], row['cislo'], row['psc'], row['obec']) or '-',
            'obec': clean_field(row['obec']) or '-',
            'lat': row['lat'],
            'lon': row['lon'],
            'obor_pece': clean_field(row['obor_pece']) or '-',
            'druh_zarizeni': clean_field(row['druh_zarizeni']) or '-',
            'forma_pece': clean_field(row['forma_pece']) or '-',
            'oddelenia': [o['nazov_oddelenia'] for o in oddelenia] if oddelenia else [],
        })

    db.close()
    return jsonify({'total': total, 'page': page, 'limit': limit, 'results': results})


@app.route('/api/detail/<int:zariadenie_id>')
def api_detail(zariadenie_id):
    db = get_db()

    row = db.execute("SELECT * FROM zariadenia WHERE id = ?", (zariadenie_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({'error': 'Zariadenie nenájdené'}), 404

    oddelenia = db.execute(
        "SELECT DISTINCT nazov_oddelenia FROM oddelenia WHERE ico = ?",
        (row['ico'],)
    ).fetchall()

    # Ordinačné hodiny
    hodiny_raw = db.execute("""
        SELECT oddelenie, den, dopoledne, odpoledne 
        FROM otvaracie_hodiny 
        WHERE ico = ? AND ruian_kod = ?
        ORDER BY oddelenie, 
            CASE den 
                WHEN 'Po' THEN 1 WHEN 'Út' THEN 2 WHEN 'St' THEN 3 
                WHEN 'Čt' THEN 4 WHEN 'Pá' THEN 5 WHEN 'So' THEN 6 
                WHEN 'Ne' THEN 7 END
    """, (row['ico'], row['ruian_kod'])).fetchall()

    hodiny = {}
    has_any_real_hours = False
    for h in hodiny_raw:
        odd = h['oddelenie']
        if odd not in hodiny:
            hodiny[odd] = {}
        val = format_hodiny(h['dopoledne'], h['odpoledne'])
        hodiny[odd][h['den']] = val
        if val is not None and val != 'zavřeno':
            has_any_real_hours = True

    hodiny_list = []
    if hodiny_raw:
        for k, v in hodiny.items():
            hodiny_list.append({'oddelenie': k, 'hodiny': v})

    # nedostupne = v DB sú záznamy ale všetky sú x/x
    # ziadne = v DB nie sú žiadne záznamy pre toto zariadenie
    hodiny_status = 'available' if has_any_real_hours else ('nedostupne' if hodiny_raw else 'ziadne')

    # Najbližšie 3 lekárne
    nearest = []
    if row['lat'] and row['lon']:
        all_pharm = db.execute(
            "SELECT * FROM lekarne WHERE lat IS NOT NULL"
        ).fetchall()
        distances = []
        for p in all_pharm:
            d = haversine(row['lat'], row['lon'], p['lat'], p['lon'])
            distances.append((d, p))
        distances.sort(key=lambda x: x[0])
        for d, p in distances[:3]:
            nearest.append({
                'nazov': clean_field(p['nazov']) or '-',
                'adresa': build_address(p['ulice'], p['cislo'], p['psc'], p['obec']) or '-',
                'vzdialenost_km': round(d, 2),
                'lat': p['lat'],
                'lon': p['lon']
            })

    result = {
        'id': row['id'],
        'ico': clean_field(row['ico']) or '-',
        'nazov': clean_field(row['nazov']) or '-',
        'adresa': build_address(row['ulice'], row['cislo'], row['psc'], row['obec']) or '-',
        'obec': clean_field(row['obec']) or '-',
        'kraj': clean_field(row['kraj']) or '-',
        'okres': clean_field(row['okres']) or '-',
        'lat': row['lat'],
        'lon': row['lon'],
        'obor_pece': clean_field(row['obor_pece']) or '-',
        'druh_zarizeni': clean_field(row['druh_zarizeni']) or '-',
        'forma_pece': clean_field(row['forma_pece']) or '-',
        'telefon': clean_field(row['telefon']) or '-',
        'email': clean_field(row['email']) or '-',
        'web': clean_field(row['web']) or '-',
        'oddelenia': [o['nazov_oddelenia'] for o in oddelenia] if oddelenia else [],
        'otvaracie_hodiny': hodiny_list,
        'hodiny_status': hodiny_status,
        'najblizsia_lekaren': nearest
    }

    db.close()
    return jsonify(result)


@app.route('/api/search_nearby')
def api_search_nearby():
    """Vyhľadá zariadenia zoradené podľa vzdialenosti od zadaných súradníc."""
    q = request.args.get('q', '').strip()
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    page = int(request.args.get('page', 0))
    limit = int(request.args.get('limit', 50))

    if lat is None or lon is None:
        return jsonify({'error': 'lat and lon are required'}), 400

    db = get_db()

    if not q:
        all_rows = db.execute("""
            SELECT * FROM zariadenia
            WHERE je_lekarna = 0 AND lat IS NOT NULL
        """).fetchall()
    else:
        q_norm = normalize(q)
        terms = q_norm.split()

        matching_icos_odd = set()
        all_odd = db.execute("SELECT ico, nazov_oddelenia FROM oddelenia").fetchall()
        for row in all_odd:
            if all(t in normalize(row['nazov_oddelenia']) for t in terms):
                matching_icos_odd.add(row['ico'])

        all_zar = db.execute("""
            SELECT * FROM zariadenia
            WHERE je_lekarna = 0 AND lat IS NOT NULL
        """).fetchall()

        all_rows = []
        for row in all_zar:
            searchable = normalize(' '.join([
                row['nazov'] or '', row['obec'] or '',
                row['obor_pece'] or '', row['druh_zarizeni'] or '',
                row['ico'] or ''
            ]))
            if row['ico'] in matching_icos_odd or all(t in searchable for t in terms):
                all_rows.append(row)

    rows_with_dist = []
    for row in all_rows:
        if row['lat'] and row['lon']:
            dist = haversine(lat, lon, row['lat'], row['lon'])
            rows_with_dist.append((dist, row))

    rows_with_dist.sort(key=lambda x: x[0])
    total = len(rows_with_dist)
    page_rows = rows_with_dist[page * limit:(page + 1) * limit]

    results = []
    for dist, row in page_rows:
        oddelenia = db.execute(
            "SELECT DISTINCT nazov_oddelenia FROM oddelenia WHERE ico = ?",
            (row['ico'],)
        ).fetchall()
        results.append({
            'id': row['id'],
            'ico': clean_field(row['ico']) or '-',
            'nazov': clean_field(row['nazov']) or '-',
            'adresa': build_address(row['ulice'], row['cislo'], row['psc'], row['obec']) or '-',
            'obec': clean_field(row['obec']) or '-',
            'lat': row['lat'], 'lon': row['lon'],
            'obor_pece': clean_field(row['obor_pece']) or '-',
            'druh_zarizeni': clean_field(row['druh_zarizeni']) or '-',
            'forma_pece': clean_field(row['forma_pece']) or '-',
            'oddelenia': [o['nazov_oddelenia'] for o in oddelenia] if oddelenia else [],
            'vzdialenost_km': round(dist, 2),
        })

    db.close()
    return jsonify({'total': total, 'page': page, 'limit': limit, 'results': results})


@app.route('/api/suggestions')
def api_suggestions():
    db = get_db()
    oddelenia = db.execute(
        "SELECT DISTINCT nazov_oddelenia FROM oddelenia ORDER BY nazov_oddelenia"
    ).fetchall()
    obory = db.execute(
        "SELECT DISTINCT obor_pece FROM zariadenia WHERE obor_pece != '' AND je_lekarna = 0"
    ).fetchall()
    obory_set = set()
    for o in obory:
        for part in (o['obor_pece'] or '').split(','):
            part = part.strip()
            if part:
                obory_set.add(part)
    all_terms = sorted(set(o['nazov_oddelenia'] for o in oddelenia) | obory_set)
    db.close()
    return jsonify(all_terms)


@app.route('/api/stats')
def api_stats():
    db = get_db()
    stats = {}
    for table in ['zariadenia', 'oddelenia', 'otvaracie_hodiny', 'lekarne']:
        stats[table] = db.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()['c']
    stats['zariadenia_bez_lekarni'] = db.execute(
        "SELECT COUNT(*) as c FROM zariadenia WHERE je_lekarna = 0"
    ).fetchone()['c']
    db.close()
    return jsonify(stats)


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print("Databáza neexistuje. Spusti najprv: python create_db.py")
        exit(1)
    app.run(debug=True, host='0.0.0.0', port=5000)