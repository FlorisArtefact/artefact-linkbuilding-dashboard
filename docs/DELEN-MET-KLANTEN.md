# Dashboard delen met een klant (statische snapshot + toegang per e-mail)

Stand 13-11-2026. Doel: elke klant een link met toegang via e-mail of wachtwoord, zonder serverkosten en zonder dat een klant iets kan doen met Ahrefs-credits.

## 1. Snapshot maken (jij of Claude, lokaal)
```
python tools/export_snapshot.py --config clients/hornbach.json --out site/hornbach
python tools/export_snapshot.py --config config.json --out site/bwj
python tools/export_snapshot.py --config config.example.json --out site/demo     # demodata, voor de eerste test
```
- Het draait het dashboard in klantweergave, per markt, en schrijft alles naar `site/<klant>/index.html` plus `plotly.min.js`.
- Er worden geen Ahrefs-credits gebruikt en er komen geen API-sleutels in het bestand.
- `site/` staat in `.gitignore`: klantdata gaat niet naar de repo.
- Snapshot = vaste momentopname. Alleen de marktkeuze en de tabbladen werken; Jaar/Kwartaal/Maand staan vast op de standaard.
- Eén keer per maand opnieuw exporteren en opnieuw uploaden.

## 2. Waarom een Cloudflare-account? (en wie heeft wat nodig)
- **Jij (eigenaar) hebt één account nodig** om de site te plaatsen en de toegangsregel in te stellen. Dat kan met elk e-mailadres, ook een Gmail-adres, het is alleen het inlogadres voor het beheer.
- **Klanten (kijkers) hebben geen account nodig.** Ze vullen hun e-mailadres in en krijgen een code per mail (one-time PIN). Alleen adressen op jouw lijst krijgen die code.
- Jouw privé-Gmail is dus het adres waarmee je de toegang test (als kijker). Voor het beheer is een eigen account nodig, aan te maken met die Gmail of met je werkmail.

## 3. Stappen (voor jou, ik maak geen accounts aan)
Deze stappen komen uit algemene beschrijvingen en zijn nog niet door mij uitgevoerd. Controleer ze tegen de Cloudflare-documentatie en stop als er om betaalgegevens wordt gevraagd.
1. Account aanmaken op cloudflare.com (gratis).
2. Workers & Pages, nieuw project, Pages, "Upload assets" (Direct Upload). Upload de map `site/demo`. Je krijgt een adres als `naam.pages.dev`.
3. Zero Trust (gratis plan, tot 50 gebruikers): Access, Applications, "Self-hosted" toevoegen voor `naam.pages.dev`.
4. Policy: Allow, selector "Emails", vul je privé-Gmail in. Login method: One-time PIN.
5. Open `naam.pages.dev` in een privévenster: je moet om je e-mailadres gevraagd worden en een code krijgen.

## 4. Voor echte klantdata
Zet geen echte klantcijfers online voordat de test met de demo werkt. Controleer ook binnen Artefact of klantdata op een extern account mag staan (zie de richtlijnen voor AI-tools, demo's en klantdata) of dat Artefact een eigen omgeving heeft.
