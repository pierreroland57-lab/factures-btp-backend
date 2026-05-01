from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import anthropic
import base64
import os
import re
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

SYSTEM_PROMPT = """Tu es un assistant expert en analyse de factures françaises du secteur BTP.
À partir du PDF fourni, extrais :
1. La date d'émission de la facture
2. Le nom du fournisseur / prestataire / émetteur (celui QUI envoie la facture, PAS le destinataire/client)
3. Le montant total TTC en euros

ATTENTION fournisseur : c'est la société qui ÉMET la facture (son nom apparaît en haut avec son SIRET/SIREN). Ce n'est PAS le client ni le destinataire.

Réponds UNIQUEMENT en JSON strict sans markdown ni texte avant/après :
{"date":"AAAA-MM-JJ","fournisseur":"NOM MAJUSCULES","montant":"1 245,60","confiance":"elevee","notes":""}

Règles :
- date : date d'émission. Formats : DD/MM/YYYY, YYYY-MM-DD. Si absent : "DATE_INCONNUE".
- fournisseur : raison sociale EMETTEUR en MAJUSCULES sans accents. Si absent : "FOURNISSEUR_INCONNU".
- montant : total TTC, séparateur milliers=espace, décimale=virgule, sans €. Ex: "11 550,00". Si absent : "MONTANT_INCONNU".
- confiance : "elevee" si labels explicites, "moyenne" si déduit, "incertaine" si ambigu/manquant.
- notes : remarque courte ou chaîne vide."""

@app.get("/", response_class=HTMLResponse)
def root():
    try:
        html = open("index.html", encoding="utf-8").read()
    except FileNotFoundError:
        html = "<h1>index.html introuvable</h1>"
    return html

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Fichier PDF uniquement")

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 20 Mo)")

    b64 = base64.standard_b64encode(content).decode("utf-8")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Clé API non configurée")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": b64
                    }
                },
                {
                    "type": "text",
                    "text": f"Analyse cette facture (fichier : \"{file.filename}\") et extrais les informations en JSON."
                }
            ]
        }]
    )

    raw = message.content[0].text
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise HTTPException(status_code=500, detail="Réponse inattendue de Claude")

    return json.loads(match.group())
