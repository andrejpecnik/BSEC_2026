"""
app.py — Flask backend pre ZdravDash.
Všetky dáta pochádzajú z SQLite databázy (naplnenej z CSV).
"""
import sqlite3
import os
from math import radians, cos, sin, asin, sqrt
from flask import Flask, render_template, request, jsonify

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))
DB_PATH = os.path.join(os.path.dirname(__file__), 'MedicApp.db')


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

    # Filters
    f_pristup = request.args.getlist('pristup')
    f_poistovna = request.args.getlist('poistovna')
    f_wc = request.args.get('wc')

    db = get_db()

    # Build dynamic WHERE
    where_parts = ["je_lekarna = 0", "lat IS NOT NULL"]
    where_params = []

    if f_pristup:
        ph = ','.join('?' * len(f_pristup))
        where_parts.append(f"pristup IN ({ph})")
        where_params.extend(f_pristup)
    if f_wc == '1':
        where_parts.append("wc = 1")

    poistovna_icos = None
    if f_poistovna:
        ph = ','.join('?' * len(f_poistovna))
        poistovna_icos = set(r['ico'] for r in db.execute(
            f"SELECT DISTINCT ico FROM poistovne WHERE poistovna IN ({ph})", f_poistovna
        ).fetchall())

    where = ' AND '.join(where_parts)

    if not q:
        all_rows = db.execute(
            f"SELECT * FROM zariadenia WHERE {where} ORDER BY nazov",
            where_params
        ).fetchall()
        if poistovna_icos is not None:
            all_rows = [r for r in all_rows if r['ico'] in poistovna_icos]
        total = len(all_rows)
        rows = all_rows[offset:offset + limit]
    else:
        q_norm = normalize(q)
        terms = q_norm.split()

        matching_icos_odd = set()
        all_odd = db.execute("SELECT ico, nazov_oddelenia FROM oddelenia").fetchall()
        for row in all_odd:
            if all(t in normalize(row['nazov_oddelenia']) for t in terms):
                matching_icos_odd.add(row['ico'])

        all_zar = db.execute(
            f"SELECT id, ico, nazov, obec, obor_pece, druh_zarizeni FROM zariadenia WHERE {where}",
            where_params
        ).fetchall()

        matching_ids = []
        for row in all_zar:
            if poistovna_icos is not None and row['ico'] not in poistovna_icos:
                continue
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

        poistovne = db.execute(
            "SELECT DISTINCT poistovna FROM poistovne WHERE ico = ? ORDER BY poistovna",
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
            'poistovne': [p['poistovna'] for p in poistovne] if poistovne else [],
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

    # Najbližšie 2 MHD zastávky
    nearest_mhd = []
    if row['lat'] and row['lon']:
        all_stops = db.execute(
            "SELECT * FROM mhd_zastavky WHERE lat IS NOT NULL"
        ).fetchall()
        stop_distances = []
        for s in all_stops:
            d = haversine(row['lat'], row['lon'], s['lat'], s['lon'])
            stop_distances.append((d, s))
        stop_distances.sort(key=lambda x: x[0])
        seen_names = set()
        for d, s in stop_distances:
            name = s['nazov']
            if name in seen_names:
                continue
            seen_names.add(name)
            nearest_mhd.append({
                'nazov': name,
                'vzdialenost_km': round(d, 2),
                'vzdialenost_m': round(d * 1000),
                'lat': s['lat'],
                'lon': s['lon'],
                'zona': clean_field(s['zona']) or '-',
                'wheelchair': s['wheelchair_boarding']
            })
            if len(nearest_mhd) >= 2:
                break

    # Poisťovne
    poistovne = db.execute(
        "SELECT DISTINCT poistovna FROM poistovne WHERE ico = ? ORDER BY poistovna",
        (row['ico'],)
    ).fetchall()

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
        'pristup': clean_field(row['pristup']) if row['pristup'] else None,
        'wc': row['wc'],
        'oddelenia': [o['nazov_oddelenia'] for o in oddelenia] if oddelenia else [],
        'otvaracie_hodiny': hodiny_list,
        'hodiny_status': hodiny_status,
        'najblizsia_lekaren': nearest,
        'najblizsia_mhd': nearest_mhd,
        'poistovne': [p['poistovna'] for p in poistovne] if poistovne else [],
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

    # Filters
    f_pristup = request.args.getlist('pristup')
    f_poistovna = request.args.getlist('poistovna')
    f_wc = request.args.get('wc')

    if lat is None or lon is None:
        return jsonify({'error': 'lat and lon are required'}), 400

    db = get_db()

    where_parts = ["je_lekarna = 0", "lat IS NOT NULL"]
    where_params = []
    if f_pristup:
        ph = ','.join('?' * len(f_pristup))
        where_parts.append(f"pristup IN ({ph})")
        where_params.extend(f_pristup)
    if f_wc == '1':
        where_parts.append("wc = 1")

    poistovna_icos = None
    if f_poistovna:
        ph = ','.join('?' * len(f_poistovna))
        poistovna_icos = set(r['ico'] for r in db.execute(
            f"SELECT DISTINCT ico FROM poistovne WHERE poistovna IN ({ph})", f_poistovna
        ).fetchall())

    where = ' AND '.join(where_parts)

    if not q:
        all_rows = db.execute(
            f"SELECT * FROM zariadenia WHERE {where}", where_params
        ).fetchall()
        if poistovna_icos is not None:
            all_rows = [r for r in all_rows if r['ico'] in poistovna_icos]
    else:
        q_norm = normalize(q)
        terms = q_norm.split()

        matching_icos_odd = set()
        all_odd = db.execute("SELECT ico, nazov_oddelenia FROM oddelenia").fetchall()
        for row in all_odd:
            if all(t in normalize(row['nazov_oddelenia']) for t in terms):
                matching_icos_odd.add(row['ico'])

        all_zar = db.execute(
            f"SELECT * FROM zariadenia WHERE {where}", where_params
        ).fetchall()

        all_rows = []
        for row in all_zar:
            if poistovna_icos is not None and row['ico'] not in poistovna_icos:
                continue
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
        poistovne = db.execute(
            "SELECT DISTINCT poistovna FROM poistovne WHERE ico = ? ORDER BY poistovna",
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
            'poistovne': [p['poistovna'] for p in poistovne] if poistovne else [],
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


# ==================== AI CHAT (Gemini) ====================

def get_ai_client():
    """Inicializácia Vertex AI klienta."""
    try:
        from google import genai
        creds_path = os.path.join(os.path.dirname(__file__), 'red-splice-488519-s6-60554b78a80a.json')
        if os.path.exists(creds_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        client = genai.Client(vertexai=True, project="red-splice-488519-s6")
        return client
    except Exception as e:
        print(f"AI client error: {e}")
        return None


def build_ai_system_prompt():
    """Systémový prompt pre Gemini s popisom DB."""
    db = get_db()

    # Unikátne oddelenia
    oddelenia = db.execute(
        "SELECT DISTINCT nazov_oddelenia FROM oddelenia ORDER BY nazov_oddelenia"
    ).fetchall()
    odd_list = [o['nazov_oddelenia'] for o in oddelenia]

    # Unikátne obce
    obce = db.execute(
        "SELECT DISTINCT obec FROM zariadenia WHERE je_lekarna = 0 AND obec != '' ORDER BY obec"
    ).fetchall()
    obce_list = [o['obec'] for o in obce]

    # Unikátne poisťovne
    poistovne = db.execute("SELECT DISTINCT poistovna FROM poistovne ORDER BY poistovna").fetchall()
    poist_list = [p['poistovna'] for p in poistovne]

    # Unikátne druhy zariadení
    druhy = db.execute(
        "SELECT DISTINCT druh_zarizeni FROM zariadenia WHERE je_lekarna = 0 AND druh_zarizeni != '' ORDER BY druh_zarizeni"
    ).fetchall()
    druhy_list = [d['druh_zarizeni'] for d in druhy]

    # Prístupy
    pristupy = db.execute(
        "SELECT DISTINCT pristup FROM zariadenia WHERE pristup IS NOT NULL AND pristup != ''"
    ).fetchall()
    pristup_list = [p['pristup'] for p in pristupy]

    db.close()

    return f"""Si AI asistent zdravotníckeho dashboardu pre Jihomoravský kraj (Česko).
Pomáhaš používateľom nájsť zdravotnícke zariadenia podľa ich požiadaviek.

DATABÁZA obsahuje {len(odd_list)} typov oddelení, zariadenia v {len(obce_list)} obciach.

DOSTUPNÉ FILTRE (použi ich na vyhľadávanie):
- oddelenie: názov oddelenia/oboru. Dostupné: {', '.join(odd_list[:60])}...
- obec: mesto/obec. Najčastejšie: {', '.join(obce_list[:30])}...
- poistovna: zmluvná poisťovňa. Dostupné: {', '.join(poist_list)}
- pristup: bezbariérový prístup. Hodnoty: {', '.join(pristup_list)}
- wc: WC k dispozícii. Hodnoty: 1 (áno), 0 (nie)
- druh_zarizeni: typ zariadenia. Dostupné: {', '.join(druhy_list[:20])}...

PRAVIDLÁ:
1. Na základe otázky používateľa extrahuj relevantné filtre.
2. Odpovedaj VŽDY vo formáte JSON s dvoma kľúčmi:
   - "filters": objekt s filtrami (len tie, ktoré používateľ zmienil)
   - "response": krátka ľudská odpoveď v slovenčine/češtine (2-3 vety, čo hľadáš a čo nájdeš)
3. Ak používateľ nezmieni konkrétny filter, NEDÁVAJ ho do filters.
4. Pre oddelenie použi presný názov z dostupných hodnôt (fuzzy matching — "zubár" → "Stomatologie", "očný" → "Oční (oftalmologie)", "srdce/kardio" → "Kardiologie", "kožný" → "Kožní (dermatovenerologie)", "detský lekár" → "Dětské (pediatrie)", "obvoďák" → "Všeobecné praktické lékařství", "ženský" → "Ženské (gynekologie, porodnictví)" atď.)
5. Ak používateľ pýta niečo mimo zdravotnícke vyhľadávanie, odpovedz s "filters": {{}}.
6. Ak nie si istý, opýtaj sa v "response" a daj "filters": {{}}.

PRÍKLADY:
Vstup: "Hľadám zubára v Brne čo berie VZP"
Výstup: {{"filters": {{"oddelenie": "Stomatologie", "obec": "Brno", "poistovna": "VZP"}}, "response": "Hľadám stomatologické zariadenia v Brne so zmluvou s VZP."}}

Vstup: "Kardiológia s bezbariérovým prístupom"
Výstup: {{"filters": {{"oddelenie": "Kardiologie", "pristup": "přístupné"}}, "response": "Hľadám kardiologické zariadenia s bezbariérovým prístupom v Jihomoravskom kraji."}}

Vstup: "čo je najbližšia lekáreň?"
Výstup: {{"filters": {{}}, "response": "Pre vyhľadanie najbližšej lekárne klikni na ľubovoľné zariadenie — v detaile uvidíš 3 najbližšie lekárne. Alebo mi povedz, aké zariadenie hľadáš, a ja ti ho nájdem."}}

ODPOVEDAJ LEN VALIDNÝM JSON-om, nič iné."""


@app.route('/api/ai_chat', methods=['POST'])
def api_ai_chat():
    """
    AI Chat endpoint — prijme ľudskú otázku, extrahuje filtre cez Gemini,
    vyhľadá v DB a vráti výsledky.
    """
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'Chýba správa'}), 400

    user_message = data['message'].strip()
    if not user_message:
        return jsonify({'error': 'Prázdna správa'}), 400

    # 1) Zavolať Gemini
    client = get_ai_client()
    if not client:
        return jsonify({
            'ai_response': 'AI asistent momentálne nie je dostupný. Použi klasické vyhľadávanie.',
            'filters': {},
            'results': [],
            'total': 0
        })

    system_prompt = build_ai_system_prompt()

    try:
        from google import genai
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{system_prompt}\n\nPoužívateľ: {user_message}"
        )
        ai_text = response.text.strip()

        # Parsovať JSON z odpovede
        import json as json_module
        # Odstrániť prípadné markdown backticky
        clean = ai_text.replace('```json', '').replace('```', '').strip()
        parsed = json_module.loads(clean)

        filters = parsed.get('filters', {})
        ai_response = parsed.get('response', 'Hľadám...')

    except Exception as e:
        print(f"Gemini error: {e}")
        return jsonify({
            'ai_response': f'Chyba pri komunikácii s AI: {str(e)}',
            'filters': {},
            'results': [],
            'total': 0
        })

    # 2) Vyhľadať v DB podľa filtrov
    db = get_db()

    conditions = ["je_lekarna = 0", "lat IS NOT NULL"]
    params = []

    if 'oddelenie' in filters:
        # Nájdi IČO cez oddelenia tabuľku
        matching_icos = db.execute(
            "SELECT DISTINCT ico FROM oddelenia WHERE nazov_oddelenia LIKE ?",
            (f"%{filters['oddelenie']}%",)
        ).fetchall()
        ico_set = [r['ico'] for r in matching_icos]
        if ico_set:
            placeholders = ','.join('?' * len(ico_set))
            conditions.append(f"ico IN ({placeholders})")
            params.extend(ico_set)
        else:
            # Fallback: hľadaj v obor_pece
            conditions.append("obor_pece LIKE ?")
            params.append(f"%{filters['oddelenie']}%")

    if 'obec' in filters:
        conditions.append("obec LIKE ?")
        params.append(f"%{filters['obec']}%")

    if 'pristup' in filters:
        conditions.append("pristup = ?")
        params.append(filters['pristup'])

    if 'wc' in filters:
        conditions.append("wc = ?")
        params.append(int(filters['wc']))

    if 'druh_zarizeni' in filters:
        conditions.append("druh_zarizeni LIKE ?")
        params.append(f"%{filters['druh_zarizeni']}%")

    where = " AND ".join(conditions)
    query = f"SELECT * FROM zariadenia WHERE {where} ORDER BY nazov LIMIT 50"
    rows = db.execute(query, params).fetchall()

    # Ak je filter na poisťovňu, dofiltrovať
    if 'poistovna' in filters:
        filtered_rows = []
        for row in rows:
            poist = db.execute(
                "SELECT poistovna FROM poistovne WHERE ico = ? AND poistovna = ?",
                (row['ico'], filters['poistovna'])
            ).fetchone()
            if poist:
                filtered_rows.append(row)
        rows = filtered_rows

    # Total count
    count_query = f"SELECT COUNT(*) FROM zariadenia WHERE {where}"
    total = db.execute(count_query, params).fetchone()[0]

    # Formátovať výsledky
    results = []
    for row in rows[:20]:  # Max 20 pre chat
        oddelenia = db.execute(
            "SELECT DISTINCT nazov_oddelenia FROM oddelenia WHERE ico = ?",
            (row['ico'],)
        ).fetchall()
        poistovne = db.execute(
            "SELECT DISTINCT poistovna FROM poistovne WHERE ico = ? ORDER BY poistovna",
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
            'poistovne': [p['poistovna'] for p in poistovne] if poistovne else [],
            'pristup': clean_field(row['pristup']),
        })

    db.close()

    return jsonify({
        'ai_response': ai_response,
        'filters': filters,
        'results': results,
        'total': len(results)
    })


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print("Databáza neexistuje. Spusti najprv: python create_db.py")
        exit(1)
    app.run(debug=True, host='0.0.0.0', port=5000)