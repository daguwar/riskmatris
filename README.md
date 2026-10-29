# Riskmatris Live

En öppen, interaktiv webbapplikation i realtid för att genomföra riskbedömningar i grupp (t.ex. tillsammans med en PowerPoint-presentation).

## Funktioner

- **Öppen för alla (ingen inloggning):** Mötesledaren startar en session och får ett unikt 6-teckens sessions-ID, en **QR-kod** och en delningslänk. Deltagare skannar QR-koden med mobilen och kommer direkt in i röstningsvyn helt anonymt.
- **Stegvis röstning per risk (`#1`, `#2`, `#3`...):**
  - **Sannolikhet (X-axeln, 1–4):** `1 – Osannolik`, `2 – Möjlig`, `3 – Sannolik`, `4 – Mycket sannolik`.
  - **Konsekvens (Y-axeln, 1–4):** `1 – Försumbar`, `2 – Måttlig`, `3 – Allvarlig`, `4 – Mycket allvarlig`.
- **Automatisk visning vid rösttröskel:** Resultatet hålls dolt tills tillräckligt många svar kommit in (standard: `min(4, antal anslutna deltagare)`), eller när mötesledaren klickar på **"Visa resultat nu"**. Kommer fler svar in efteråt uppdateras matrisen i realtid.
- **4×4 Riskmatris (Sannolikhet × Konsekvens = 1–16):**
  - **Grön (1–2):** Låg risk
  - **Gul (3–6):** Medelrisk
  - **Orange (8–9):** Hög risk
  - **Röd (12–16):** Mycket hög risk
- **Beräknat förslag & Sammanställningsmatris:**
  - Visar både röstspridningen (antal röster per ruta) och beräknat medelvärde (avrundat uppåt vid `.5` enligt försiktighetsprincipen).
  - Mötesledaren kan godkänna förslaget eller klicka på valfri ruta i matrisen efter diskussion för att låsa placeringen av `#1`, `#2` osv. till **Sammanställningsmatrisen**.
- **Export till PowerPoint & Excel:**
  - **PNG-bild:** Ladda ner en högupplöst bild av sammanställningsmatrisen med alla inplacerade risker (`#1`, `#2`...) redo att klistras in i PowerPoint.
  - **CSV (Excel):** Exportera en tabell med alla risker, röstantal, medelvärden, beslutad Sannolikhet/Konsekvens, Riskvärde och Risknivå.

---

## Köra applikationen

### 1. Köra lokalt (manuellt, utan Docker)

Skapa en virtuell Python-miljö, installera beroenden och starta servern i terminalen:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Öppna sedan **http://localhost:8000** i webbläsaren.
*(Om du öppnar via `localhost` pekar QR-koden automatiskt på datorns lokala nätverks-IP så att deltagare på samma Wi-Fi kan skanna koden med sina mobiler.)*

### 2. Köra med Docker

```bash
docker compose up --build -d
```

Applikationen nås då på **http://localhost:8000** och sparar pågående sessioner i en Docker-volym (`riskmatris_data`) så att de överlever en omstart. Sessioner rensas automatiskt efter 48 timmar.

### 3. Köra i molnet (Render, Fly.io, Google Cloud Run, Azure App Service)

Eftersom projektet har både `Dockerfile` och `requirements.txt` samt lyssnar på miljövariabeln `PORT` kan du ladda upp projektet direkt till valfri molntjänst utan ändringar.

### 4. Köra på egen server bakom befintlig Traefik (HTTPS)

Har du en server där Traefik redan sköter HTTPS och certifikat kör du appen **utan publicerade portar** – Traefik routar trafiken till containern via ett gemensamt Docker-nätverk (labels på containern, se `docker-compose.traefik.yml`):

```bash
cp .env.example .env    # fyll i dina värden
docker compose -f docker-compose.traefik.yml up -d --build
```

Fyll i i `.env`:

- `RISKMATRIS_DOMAIN` – domänen Traefik ska svara på (obligatorisk), t.ex. `riskmatris.example.com`
- `TRAEFIK_NETWORK` – namnet på Docker-nätverket din Traefik kör på (ofta `traefik-public`; nätverket måste redan finnas)
- `TRAEFIK_ENTRYPOINT` / `TRAEFIK_CERT_RESOLVER` – namn på entrypoint och cert-resolver (standard: `websecure` / `letsencrypt`)

Öppna appen via din domän (`https://riskmatris.example.com`). Delningslänk och QR-kod pekar då automatiskt på rätt adress, och WebSockets (`wss://`) fungerar genom Traefik utan extra konfiguration. Vill du felsöka lokalt på servern kan du lägga till `ports: - "127.0.0.1:8000:8000"` i compose-filen (bind då endast till localhost).

