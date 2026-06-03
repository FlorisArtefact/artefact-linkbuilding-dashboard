# Artefact — Linkbuilding Dashboard

Professioneel linkbuilding dashboard voor gebruik bij Artefact-klanten.
Leest data uit een Excel-database, toont KPIs per taal, en integreert met Ahrefs en Google Search Console.

---

## Lokaal starten

```bash
# 1. Installeer dependencies
pip install -r requirements.txt

# 2. Maak een .env bestand aan
cp .env.example .env
# Vul je Ahrefs API key in in .env

# 3. Zet de Excel-database in de data/ map
#    en pas excel_path aan in config.json

# 4. Start het dashboard
streamlit run app.py
```

Het dashboard opent op http://localhost:8501

---

## Nieuwe klant instellen

1. Kopieer dit project naar een nieuwe map
2. Pas `config.json` aan:
   ```json
   {
     "client_name": "Naam klant",
     "excel_path": "data/klant-database.xlsx",
     "languages": ["NL", "EN"],
     "domains": {
       "NL": "domein.nl",
       "EN": "domain.com"
     }
   }
   ```
3. Zet de Excel in `data/`
4. Stel een nieuwe `.env` in met de Ahrefs API key
5. Start met `streamlit run app.py`

---

## Google Search Console koppelen (gratis)

De Search Console API kost niets — je hebt er alleen een Google Cloud project voor nodig (dat je waarschijnlijk al hebt).

### Stap 1 — API inschakelen

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com)
2. Selecteer je project (of maak een nieuw project)
3. Navigeer naar **APIs & Services → Library**
4. Zoek op **"Google Search Console API"**
5. Klik **Enable**

### Stap 2 — OAuth credentials aanmaken

1. Ga naar **APIs & Services → Credentials**
2. Klik **+ Create Credentials → OAuth Client ID**
3. Application type: **Desktop app**
4. Naam: bijv. `Artefact Linkbuilding Dashboard`
5. Klik **Create** → download het `credentials.json` bestand

### Stap 3 — Bestand plaatsen

Zet `credentials.json` in de root van het dashboard:

```
linkbuilding-dashboard/
├── credentials.json   ← hier plaatsen
├── app.py
└── ...
```

### Stap 4 — GSC data exporteren (tussenoplossing)

Zolang de volledige OAuth-flow nog niet is gebouwd, kun je GSC-data handmatig exporteren:

1. Ga naar [search.google.com/search-console](https://search.google.com/search-console)
2. Selecteer de property
3. Klik op **Prestaties → Pagina's**
4. Stel de gewenste datumperiode in
5. Klik op **Exporteren → Download als CSV**
6. Upload het CSV-bestand in de sidebar van het dashboard

Het dashboard matcht automatisch de GSC-positiedata aan de landing pages in je Excel.

---

## Ahrefs API

Het dashboard gebruikt de Ahrefs API v3 voor:
- **Gem. organische positie** per landing page
- **Organisch verkeer** schatting
- **Aantal rankende keywords**

Zet je API key in `.env`:
```
AHREFS_API_KEY=jouw_key_hier
```

Of voer hem in via de sidebar van het dashboard.

---

## Deployen naar Streamlit Cloud

1. Zet het project op GitHub (zorg dat `.env` en `data/*.xlsx` in `.gitignore` staan)
2. Ga naar [share.streamlit.io](https://share.streamlit.io)
3. Koppel je GitHub repo
4. Voeg secrets toe via **App settings → Secrets**:
   ```toml
   AHREFS_API_KEY = "jouw_key_hier"
   ```
5. De Excel kun je uploaden via de sidebar, of via een Google Drive/SharePoint koppeling

---

## Excel-structuur

Het dashboard verwacht de volgende sheetstructuur:

| Sheet | Inhoud |
|-------|--------|
| `Live_links_NL` | Geplaatste backlinks NL |
| `Live_links_EN` | Geplaatste backlinks EN |
| `Live_links_DE` | Geplaatste backlinks DE |
| `Opportunities_NL` | Pipeline NL |
| `Opportunities_EN` | Pipeline EN |
| `Opportunities_DE` | Pipeline DE |

Vereiste kolommen per Live_links sheet:
`Q, Invoiced Month, Year, LL Date, Live Link, Status code, DA, Backlink/Brand Mention, Link Type, Domain, Link to, Anchor text, Price, Target campaign`
