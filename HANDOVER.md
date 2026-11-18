# 🔗 BWJ Linkbuilding Dashboard → ROI & Budgetadvies-tool — Project Overdracht

> **Voor de volgende Claude-sessie die dit oppakt (nieuwe laptop, Claude Enterprise).**
> **Lees dit hele bestand voordat je ook maar één regel code schrijft.** Dit is geen simpele "maak het dashboard af"-taak meer — de doelstelling is verbreed. Onderaan staat een lijst met vragen die je EERST met Floris moet doorlopen, vóór je gaat bouwen.

---

## TL;DR voor Floris

- De **live dashboards (BWJ en ACT) zijn volledig laptop-onafhankelijk** — ze draaien op GitHub + Streamlit Cloud, niet op deze machine. Een nieuwe laptop verandert daar niets aan.
- Voor **lokale ontwikkeling** op de nieuwe laptop moet je 2 kleine bestanden overzetten (zie "Credentials" hieronder) — niet nodig om de live dashboards te laten draaien, wel nodig om lokaal te kunnen testen/bouwen.
- Het project heeft een **nieuwe, grotere missie** gekregen (je H2 2026-doel, hieronder volledig opgenomen) — dit is een scope-verbreding, geen "dashboard afmaken."
- Voordat de ROI-module gebouwd wordt, moet de volgende Claude-sessie eerst een aantal aannames met je challengen — zie "🔥 Vragen die eerst beantwoord moeten worden."
- **Urgente actie:** toegang vragen tot GA4 van BWJ (conceptbericht hieronder) — dit blokkeert de hele ROI-berekening.

---

## 🎯 De missie (H2 2026-doel — letterlijk van Floris)

**Linkbuildingdashboard van rapportage naar herbruikbaar ROI- en budgetadviesinstrument**

Ik bouw voort op het bestaande BWJ linkbuildingdashboard, ik begin dus niet vanaf 0, en verbreed de impact door er een standaard ROI- en budgetadviesmodule van te maken die herhaalbaar inzetbaar is voor meerdere klanten. Het dashboard laat niet alleen zien wat we hebben gedaan, maar vooral wat de investering oplevert en of het verstandig is om het budget te behouden, te verhogen of te verlagen. Met disclaimers, omdat het prognoses zijn en geen garanties. Het blijft immers een black box: Google's algoritme.

**Dit ga ik opleveren:**
- Een standaard ROI berekening met duidelijke aannames. Als een directe koppeling met omzet niet mogelijk is, werk ik met een laag, realistisch en hoog scenario.
- Een vaste managementsamenvatting in het dashboard met de uitkomst én een concreet budgetadvies (behouden, verhogen of verlagen).
- Deze ROI- en budgetadviesmodule maak ik generiek herbruikbaar als template, zodat een collega hem voor een andere klant kan inzetten zonder het dashboard opnieuw te bouwen.
- Afstemming van de te gebruiken gegevens en aannames met BWJ, interne collega's en de pillar leads. Denk aan investering, geplaatste links, kwaliteit, rankings, organisch verkeer, conversies en omzet of leadwaarde als die beschikbaar zijn.
- Een test van de module met BWJ en minimaal één andere klant.

**Wanneer is dit doel behaald?**
- Het dashboard laat zowel de SEO resultaten als de mogelijke businesswaarde zien en geeft een duidelijk budgetadvies.
- De ROI- en budgetadviesmodule is als herbruikbare standaard/template opgezet en werkt aantoonbaar voor minimaal één andere klant naast BWJ.
- De berekening en aannames zijn afgestemd met de betrokken collega's.

**Deadline:** einde H2 2026.

---

## 💬 Stakeholder feedback — Arlette van Opzeeland (letterlijk, uit comments in de Google Sheet)

> **Arlette van Opzeeland — 18:14, 1 sept**
> "we hebben in het verleden al meerdere keer nieuwe tools aangeschaft. Voor het behalen van dit doel lijkt het nu alsof we een nieuwe tool moeten aanschaffen. Ik zou je graag willen vragen om te kijken hoe we dingen kunnen doen zonder extra geld uit te geven."

> **Arlette van Opzeeland — 09:18, 2 sept**
> "budget verwoording aanpassen naar zelf onderzoeken gratis variant om dit te doen of mogelijk google cloud? om een gratis / niet betaalde versie focus te geven hierop"

**Wat dit concreet betekent:** geen nieuwe betaalde SaaS-tools. Alles moet op gratis lagen draaien — Google Cloud (al in gebruik, binnen het gratis quotum), Streamlit Community Cloud (gratis), GitHub (gratis). Als iets een betaalde upgrade nodig heeft (bijv. Streamlit Teams voor onbeperkt privé-apps), moet dat expliciet als "infrastructuur" aan Arlette worden voorgelegd — niet stilzwijgend toegevoegd.

---

## 🔥 Instructies voor de volgende Claude-sessie: challenge Floris eerst

Floris heeft hier expliciet om gevraagd: **begin niet meteen met bouwen.** Loop eerst deze punten met hem door — ze veranderen het ontwerp wezenlijk:

1. **Omzetdata-realitycheck.** Heeft BWJ's GA4-property überhaupt ecommerce/omzet-tracking ingericht? Zo niet, geeft `totalRevenue` altijd 0 terug — zelfs met volledige API-toegang — en valt het hele "omzet-gekoppelde ROI"-plan terug op een verkeerswaarde-proxy. Check dit vóórdat er gebouwd wordt, niet erna.
2. **Wat betekent "ROI" hier precies?** Omzet ÷ kosten? Of incrementele omzet (t.o.v. een baseline zonder linkbuilding) ÷ kosten? Het doel noemt laag/realistisch/hoog-scenario's — wat is de daadwerkelijke modelleringsaanname achter elk scenario (bijv. welk % van een rankingverbetering wordt toegeschreven aan de link versus andere SEO-inspanning)?
3. **Eigendom van het GCP-project.** De service account draait momenteel in `seo-pagespeed-insights-352108` — Floris' **persoonlijke** Google Cloud project, niet een door Artefact beheerd project. Is dat acceptabel op de lange termijn voor een tool die commercieel gevoelige data van meerdere klanten gaat bevatten (omzet, budgetten)? Dit verdient aandacht van IT/security voordat dit "de standaard template" wordt.
4. **Keuze tweede klant.** ACT is al aangesloten, maar heeft alleen een NL-tabblad met 9 historische links — is dat genoeg data om overtuigend te bewijzen dat de ROI-module generaliseert? Of moet een klant met meer volume/bestaande omzetdata als tweede validatiecase dienen?
5. **Plafond van de gratis laag.** Streamlit Community Cloud staat precies **één privé-app** gratis toe — zowel BWJ als ACT werken dit nu om met een wachtwoord-scherm op een technisch publieke URL. Is dat acceptabel om als "de generieke template" aan andere accountteams te presenteren, of moet er met Arlette een duidelijke lijn worden getrokken tussen infrastructuurkosten en tool-aanschaf?
6. **Wie zijn "de pillar leads"?** Het doel noemt afstemming van aannames met "collega's en de pillar leads" — namen nodig. De geloofwaardigheid van de ROI-module staat of valt met deze daadwerkelijk gevalideerde aannames, niet intern verzonnen cijfers.
7. **GA4-toegangspad.** Wie beheert de GA4-property van BWJ — BWJ zelf, of een Artefact accountmanager? Dit bepaalt of Floris rechtstreeks toegang kan vragen of via de klantrelatie moet lopen.
8. **Realiteitscheck planning.** Einde H2 2026 voor: ROI-model + managementsamenvatting + generieke template + stakeholder-afstemming + test bij 2 klanten. Is er een mijlpalenplan, of is dit één big-bang-oplevering? Stel nu samen met Floris een fasering voor.

Laat hem deze niet overslaan. Een technisch werkend dashboard waar niemand de aannames voor heeft goedgekeurd, is geen behaald doel.

---

## 📍 Huidige status (per 28-10-2026)

### Architectuur in één oogopslag

```
Google Sheet (klantdata, levend)
        ↓  (service account, read-only)
Python/Streamlit dashboard (GitHub repo)
        ↓  (auto-deploy per branch)
Streamlit Cloud (live, publiek + wachtwoord-gate)
        ↓
Klant + collega's (via gedeelde URL + wachtwoord)

Aanvullende databronnen (deels nog niet actief):
- Ahrefs API      → rankingposities, organisch verkeer      [ACTIEF]
- Google Sheets   → geplaatste links, kosten, pipeline       [ACTIEF]
- Search Console  → klikken, posities per pagina             [CODE KLAAR, toegang nog niet verleend]
- GA4             → omzet, conversies per landing page        [CODE KLAAR, property ID nog niet ingevuld]
```

### Branches & deployments

| Branch | Doel | Status | Streamlit-app |
|---|---|---|---|
| `master` | **BWJ — live productie** | Stabiel, klant gebruikt dit nu | https://artefact-linkbuilding-dashboard-mkfhxoujc6veavtkd2etgd.streamlit.app/ |
| `client-act` | **ACT — live productie** | Stabiel, klant gebruikt dit nu | *(Floris: vul hier de ACT Streamlit-URL in)* |
| `dashboard-v2` | **Nieuwste werk — nog NIET live** | Getest, klaar om te mergen naar master zodra GA4/GSC toegang is geregeld | Nog geen staging-app voor aangemaakt |

**GitHub repo (publiek):** https://github.com/FlorisArtefact/artefact-linkbuilding-dashboard

### Wat zit er in `dashboard-v2` dat nog niet live staat?

- ❌ "Link Types" donut-grafiek verwijderd (was altijd 100% dofollow, geen waarde)
- ✅ Nieuwe grafiek: Cost vs. Revenue per landing page
- ✅ GA4-integratie: omzet, conversies, ROI per landing page (code klaar, wacht op property ID + toegang)
- ✅ Search Console zonder handmatig werk — leest automatisch via API i.p.v. CSV-upload (code klaar, wacht op toegang)
- ✅ Taalondersteuning generiek gemaakt — FR/ES kunnen met één regel in `config.json` worden toegevoegd zodra de sheet-tabs bestaan
- ✅ Gedeelde `google_auth.py`-module (voorkomt dubbele credential-logica in Sheets/GSC/GA4)
- ✅ Stille fallback: als GA4/GSC-toegang nog niet is verleend, toont het dashboard gewoon geen data — **geen foutmelding zichtbaar voor de klant**

**Belangrijk:** dit is nog NIET gemerged naar `master`. Eerst testen via een staging-Streamlit-app op branch `dashboard-v2`, dan pas mergen — zodat de klant nooit downtime of fouten ziet.

### Databronnen per klant

| Klant | Google Sheet | Talen | Domeinen |
|---|---|---|---|
| **BWJ** (smartwatchbanden) | https://docs.google.com/spreadsheets/d/1ER14RidJFycvFidUkEHyQGozxhATD73iPE-YBwSbZuU | NL, EN, DE (FR/ES gepland) | smartwatchbanden.nl, smartwatch-straps.co.uk, smartwatcharmbaender.de |
| **ACT** | https://docs.google.com/spreadsheets/d/1A_D60p37kydxDK4_BhbISGh_58ALHXbXOTDF3QHpG3U | NL | *(nog niet ingevuld in config)* |

---

## 🔑 Credentials & toegang — wat bestaat, niet de waarden zelf

Dit overdrachtsbestand bevat **bewust geen geheime sleutels** — die horen niet in een los document dat kan rondslingeren. Hieronder staat wat er bestaat en waar het te vinden is.

| Wat | Waar het staat | Actie nodig bij laptop-wissel? |
|---|---|---|
| Live dashboards (BWJ + ACT) | Streamlit Cloud (cloud-gehost) | **Nee** — log in op [share.streamlit.io](https://share.streamlit.io) met hetzelfde account, alles staat er al |
| Broncode + historie | GitHub repo (publiek) | **Nee** — gewoon `git clone`, werkt op elke machine |
| Ahrefs API key | `.env` bestand (lokaal) + Streamlit Cloud secrets | Alleen kopiëren als je **lokaal** wilt ontwikkelen; live dashboards hebben hem al via Streamlit secrets |
| Google service account (JSON key) | `seo-pagespeed-insights-352108-0a7637b209fd.json` (lokaal, gitignored) + Streamlit Cloud secrets | Zelfde als hierboven — alleen voor lokale ontwikkeling nodig |
| Streamlit app-wachtwoorden (APP_PASSWORD) | Streamlit Cloud secrets per app | Nee — staat al in de cloud, Floris kent de wachtwoorden zelf |
| GCP project | `seo-pagespeed-insights-352108` (Floris' persoonlijke Google account) | Inloggen met hetzelfde Google-account volstaat |

**Bestanden om over te zetten naar de nieuwe laptop (alléén nodig voor lokale ontwikkeling, via USB/wachtwoordmanager — nooit via Slack/mail):**
1. `seo-pagespeed-insights-352108-0a7637b209fd.json` — service account sleutel
2. `.env` — bevat de Ahrefs API key

**Niets overzetten nodig om de levende klant-dashboards te laten werken** — die draaien volledig los van deze laptop.

---

## ✉️ Urgente actie: GA4-toegang vragen voor BWJ (concept)

Dit blokkeert de hele ROI-berekening — dit is de eerste stap die gezet moet worden.

**Service account e-mail (voeg dit toe als Viewer in GA4):**
```
linkbuilding-dashboard@seo-pagespeed-insights-352108.iam.gserviceaccount.com
```

**Conceptbericht aan BWJ (pas de aanhef aan naar de juiste contactpersoon):**

> Onderwerp: Toegang GA4 voor rapportage-uitbreiding linkbuilding
>
> Hoi [naam],
>
> Voor de doorontwikkeling van het linkbuilding-dashboard willen we voortaan ook omzet en conversies per landingpagina kunnen meenemen, zodat we naast de SEO-resultaten ook de business-impact van de linkbuilding-investering kunnen laten zien.
>
> Zouden jullie een service account toegang kunnen geven tot de GA4-property van [domein]? Dit kan via:
> **GA4 → Beheer → Property Access Management → Gebruikers toevoegen**
> E-mailadres: `linkbuilding-dashboard@seo-pagespeed-insights-352108.iam.gserviceaccount.com`
> Rol: **Viewer** (alleen leesrechten, geen wijzigingen mogelijk)
>
> Kunnen jullie ook aangeven of er ecommerce/omzet-tracking is ingericht in deze GA4-property? Dat is nodig om te weten of we met echte omzetcijfers kunnen werken of met een schatting.
>
> Alvast bedankt!
>
> [Floris]

**Let op:** dit is een conceptbericht, nog niet verstuurd. Vraag Floris expliciet om bevestiging voordat dit wordt verstuurd namens hem.

---

## 🚀 Hoe verder te gaan op de nieuwe laptop

```bash
# 1. Clone de repo
git clone https://github.com/FlorisArtefact/artefact-linkbuilding-dashboard.git
cd artefact-linkbuilding-dashboard

# 2. Ga naar de nieuwste werk-branch (nog niet live)
git checkout dashboard-v2

# 3. Kopieer de 2 lokale secret-bestanden hierheen (zie Credentials-sectie)

# 4. Installeer dependencies
pip install -r requirements.txt

# 5. Start lokaal
streamlit run app.py
```

Voor de **live** dashboards hoef je niets te doen — die draaien al op Streamlit Cloud.

---

## 📜 Beslissingenlog — waarom dingen zijn zoals ze zijn

Context voor de volgende Claude-sessie, zodat bestaande keuzes niet opnieuw bediscussieerd hoeven worden:

- **Service account i.p.v. OAuth** voor Google Sheets/GSC/GA4 — geen herhaalde logins nodig, werkt headless op Streamlit Cloud.
- **`UNFORMATTED_VALUE` bij Sheets-API calls** — `FORMATTED_VALUE` gaf `"€550,00"` als string terug (door celopmaak), wat `pd.to_numeric()` liet falen. Los getal nodig.
- **Streamlit Cloud i.p.v. Looker Studio** — Floris wilde meer controle en een professionelere, merk-eigen uitstraling dan Looker Studio biedt.
- **Wachtwoord-gate i.p.v. Streamlit Teams** — Streamlit Community Cloud staat maar 1 gratis privé-app toe; een simpele `APP_PASSWORD`-check in de app zelf lost dit op zonder kosten. **Dit is precies het soort gratis-oplossing die Arlette vroeg — expliciet zo benoemen als dit ter sprake komt.**
- **Stille fallback bij ontbrekende API-toegang** (GA4, GSC) — voorkomt dat de klant een ruwe foutmelding op het dashboard ziet als toegang nog niet is geregeld. Zelfde patroon als de bestaande Ahrefs-integratie.
- **Branch-per-klant + branch voor nieuw werk** — zodat een live klant-dashboard nooit per ongeluk breekt tijdens ontwikkeling. Nieuw werk wordt eerst op een aparte branch getest (evt. via een tijdelijke staging Streamlit-app) voordat het naar `master`/`client-act` wordt gemerged.
- **GA4/GSC property-matching op URL-pad, niet volledige URL** — GA4 rapporteert alleen het pad (bijv. `/collections/apple-watch-se-bandjes`), niet het volledige domein. Matching gebeurt daarom op pad, niet op exacte URL-string.

---

## ✅ Definitie van "klaar" (uit het doel, letterlijk)

- Het dashboard laat zowel de SEO resultaten als de mogelijke businesswaarde zien en geeft een duidelijk budgetadvies.
- De ROI- en budgetadviesmodule is als herbruikbare standaard/template opgezet en werkt aantoonbaar voor minimaal één andere klant naast BWJ.
- De berekening en aannames zijn afgestemd met de betrokken collega's.

---

*Dit document is zowel opgeslagen in de git-repo (`HANDOVER.md`, meereizend met elke `git clone`) als lokaal op deze laptop. Bij twijfel: de git-versie is de actuele bron van waarheid.*
