# Nieuwe klant toevoegen (ROI- en budgetsignaal-dashboard)

Eén codebase, per klant een eigen app met eigen geheimen. Klanten zien nooit elkaars data.

## 1. Wat je nodig hebt (per klant)
| Wat | Waar vandaan | Verplicht? |
|---|---|---|
| Google Sheet met tabs `Live_links_<TAAL>` (of `Live links_<TAAL>`) en `Opportunities_<TAAL>` | linkbuildingdatabase | ja |
| Service account als **Viewer** op die Sheet | zelfde account voor alle klanten | ja |
| Ahrefs API-sleutel | Artefact-abonnement (geen nieuwe tools) | aanbevolen |
| GA4 Property ID + service account als Viewer | klant | voor echte omzet-ROI, groei, referral |
| Search Console `sc-domain:` + service account | klant | voor klik- en positietrend |

Kolommen in Live links die het dashboard gebruikt: `Year`, `Q`, `LL Date`, `Live Link`, `Status code`, `DA`,
`Backlink/ Brand Mention`, `Link Type`, `Anchor text`, `Link to`, `Price` (of een kolom met "price" in de naam),
`Target campaign`. Dubbele kolomnamen worden samengevoegd.

## 2. Config schrijven
Kopieer `config.example.json` naar `clients/<klant>.json` en vul in:
- `client_name`, `languages` (tabnamen eindigen op deze codes), `domains`, `gsc_properties`, `ga4.property_ids`
- `google_sheets.spreadsheet_id`; `live_tab` / `opp_tab` alleen als de tabnamen afwijken (`"Live links_{lang}"`)
- `categories`: trefwoorden in de URL per productgroep (bijv. `"Maaltijdbox": ["maaltijdbox"]`)
- `roi`: waarde per conversie, conversieratio, aandeel van de omzet dat aan linkbuilding wordt toegeschreven
  (standaard 100% afgestemd met BWJ; **stem dit per klant af met de pillar lead**), drempels voor het advies

## 3. Lokaal testen
```bash
CONFIG_FILE=clients/<klant>.json streamlit run app.py
```
Zet in de zijbalk onder *Set-up* "Demo data" aan om zonder gegevens te oefenen.

## 4. Live zetten (één app per klant)
1. Privé GitHub-repo (niet publiek: de repo bevat klantnamen in `clients/`; zet liever alleen `config.example.json` in de repo
   en de echte config in de geheimen van de app).
2. Streamlit Community Cloud: nieuwe app, zelfde repo, **eigen secrets** per klant:
   `CLIENT_CONFIG_JSON` (inhoud van de config), `APP_PASSWORD`, `AHREFS_API_KEY`, `[gcp_service_account]`,
   optioneel `[auth]` + `ALLOWED_EMAILS` voor Google-inlog.
3. Controleer in een privévenster dat de app alleen die klant toont.

## 5. Tweede-klant-checklist
- [ ] Sheet leest zonder foutmelding, alle talen geladen
- [ ] Links, kosten en categorieën kloppen met de Sheet
- [ ] Zonder GA4 toont het dashboard "indicatief" en vraagt het niet om data die er niet is
- [ ] Aannames (waarde per conversie, aandeel) afgestemd en genoteerd
- [ ] Voorbehouden ("sturing, geen bewijs") zichtbaar
