# Live dashboard delen per e-mailadres (gratis, voor elke klant)

Stand 18-11-2026. Doel: per klant een live link waar alleen uitgenodigde e-mailadressen in kunnen, zonder kosten en zonder limiet op het aantal klanten.

## Hoe het werkt
- Elke klant krijgt een eigen app op Streamlit Community Cloud (zelfde repo, eigen secrets).
- De app staat bij Streamlit op "public", maar toont zelf eerst een scherm "Sign in with Google". Daarna laat hij alleen e-mailadressen uit de lijst `ALLOWED_EMAILS` door. Zonder login ziet niemand cijfers (getest).
- Streamlit telt alleen apps met Streamlits eigen privé-instelling mee voor de limiet van één privé-app. Deze route valt daar niet onder, dus BWJ, Hornbach en volgende klanten kunnen allemaal.
- Kijkers loggen in met een Google-account. Werkt voor Gmail en Google Workspace. Wie dat niet heeft, kan gratis een Google-account op zijn werkadres maken (zonder Gmail).

## Eenmalig: Google-inlog aanmaken (jij, ongeveer 10 minuten)
1. Google Cloud Console, bij voorkeur een Artefact-project. Het huidige project `seo-pagespeed-insights-352108` staat op je persoonlijke account.
2. Google Auth Platform: Branding (app-naam "Artefact Linkbuilding Dashboard", je e-mail), Audience: External. Zet de status op "In production". In "Testing" kunnen alleen testgebruikers inloggen. Voor alleen naam en e-mail (openid, email, profile) is geen verificatie door Google nodig.
3. Clients, Create client, type "Web application". Bij Authorized redirect URIs vul je per app de URL plus `/oauth2callback` in, bijvoorbeeld `https://<bwj-app>.streamlit.app/oauth2callback`.
4. Noteer de client ID en client secret. Zet ze nergens anders neer dan in de Streamlit-secrets.

## Per klant-app: secrets (jij plakt dit in Streamlit, app, Settings, Secrets)
```toml
ALLOWED_EMAILS = ["naam@klant.nl", "floris.broekmeulen@artefact.com"]   # "@klant.nl" laat het hele domein toe

[auth]
redirect_uri = "https://<app-url>.streamlit.app/oauth2callback"
cookie_secret = "<lange willekeurige tekst>"
client_id = "<uit stap 4>"
client_secret = "<uit stap 4>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```
De bestaande secrets (service account, Ahrefs) blijven eronder staan. `APP_PASSWORD` mag weg zodra dit werkt.

## Iemand toegang geven
Voeg het adres toe aan `ALLOWED_EMAILS`, sla op en stuur de link. De app herstart vanzelf. Toegang intrekken gaat net zo: adres weghalen.

## Nieuwe klant
1. Streamlit, Create app, zelfde repo en branch. Kies de configuratie met secret `CLIENT_CONFIG_JSON` (inhoud van `clients/<klant>.json`), zodat klantgegevens niet in de openbare repo staan.
2. Secrets zoals hierboven, met de eigen URL in `redirect_uri`. Voeg die URL ook toe in de Google-client (stap 3).
