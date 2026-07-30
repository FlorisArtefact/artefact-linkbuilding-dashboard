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

## Google Search Console koppelen (gratis, geen handmatig werk)

Gebruikt hetzelfde service account als Google Sheets — geen aparte OAuth-flow nodig.

### Stap 1 — API inschakelen

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com)
2. Selecteer hetzelfde project als voor Google Sheets
3. Navigeer naar **APIs & Services → Library**
4. Zoek op **"Search Console API"** → klik **Enable**

### Stap 2 — Service account toegang geven

1. Ga naar [search.google.com/search-console](https://search.google.com/search-console) → open de property
2. **Instellingen → Gebruikers en machtigingen → Gebruiker toevoegen**
3. Plak het e-mailadres van het service account (zie `client_email` in het JSON-bestand)
4. Rol: **Beperkt (Restricted)** is voldoende — alleen leesrechten nodig

### Stap 3 — Property URL(s) instellen

Vul de property-URL(s) in bij `gsc_properties` in `config.json`:
```json
"gsc_properties": {
  "NL": "https://voorbeeld.nl/",
  "EN": "https://example.com/"
}
```

Zodra dit is ingesteld ververst het dashboard automatisch elke 6 uur — geen CSV-export meer nodig.
Als de toegang nog niet is verleend, toont het dashboard gewoon geen GSC-data (geen foutmelding) totdat het is ingesteld.

**Fallback:** zolang de API niet is ingesteld, kun je nog altijd handmatig een CSV uploaden via de sidebar
(Prestaties → Pagina's → Exporteren → CSV).

---

## Google Analytics 4 koppelen (omzet & conversies per landing page)

Ook via hetzelfde service account.

### Stap 1 — API inschakelen

1. Zelfde Google Cloud project → **APIs & Services → Library**
2. Zoek op **"Google Analytics Data API"** → klik **Enable**

### Stap 2 — Service account toegang geven

1. In GA4: **Beheer → Property Access Management**
2. **Gebruikers toevoegen** → plak het e-mailadres van het service account
3. Rol: **Viewer**

### Stap 3 — Property ID instellen

Vind het Property ID in GA4: **Beheer → Property Settings** (een nummer, bijv. `123456789`).

```json
"ga4": {
  "property_id": "123456789"
}
```

Heeft de klant per taal een aparte GA4-property (aparte domeinen)? Gebruik dan:
```json
"ga4": {
  "property_ids": {
    "NL": "111111111",
    "EN": "222222222"
  }
}
```

Zodra dit is ingesteld toont het dashboard automatisch omzet, conversies en ROI per landing page —
geen handmatig werk, geen redeploy nodig.

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

---

## Een taal toevoegen (bijv. Frans of Spaans)

Het dashboard ondersteunt elk aantal talen zonder codewijzigingen.

1. Voeg de tabs `Live_links_FR` en `Opportunities_FR` toe aan de Google Sheet (zelfde kolomstructuur als de bestaande talen)
2. Voeg `"FR"` toe aan de `languages` array in `config.json`:
   ```json
   "languages": ["NL", "EN", "DE", "FR"]
   ```
3. Klaar — er verschijnt automatisch een nieuw tabblad in het dashboard

Zolang een taal nog niet in de `languages` array staat, negeert het dashboard die sheet volledig
(geen foutmeldingen, geen lege tabbladen). Zet talen dus pas in de config zodra de sheet-tabs echt bestaan.
