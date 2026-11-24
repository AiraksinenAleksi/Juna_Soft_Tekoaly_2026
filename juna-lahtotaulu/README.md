# Junien lähtötaulu

Python Flask -sovellus, joka hakee junien lähtötiedot Digitraffic API:sta.

## Ominaisuudet

- Helsinki (HKI)
- Tampere (TPE)
- Kokkola (KOK)
- Reaaliaikaiset lähtötiedot
- UTC-aikojen muunnos Suomen aikaan
- Myöhästymisen laskenta
- Automaattinen 30 sekunnin päivitys
- API-virheiden käsittely

## Asennus

Python 3.9 tai uudempi.

1. Luo virtuaaliympäristö:

   python -m venv venv

2. Aktivoi se Windowsissa:

   venv\Scripts\activate

   Mac/Linux:

   source venv/bin/activate

3. Asenna riippuvuudet:

   pip install -r requirements.txt

4. Käynnistä sovellus:

   python app.py

5. Avaa selain:

   http://127.0.0.1:5000

## API

- GET /api/stations
- GET /api/departures?station=HKI
- GET /api/departures?station=TPE
- GET /api/departures?station=KOK

## Tietolähde

Digitraffic Railway API:
https://rata.digitraffic.fi/swagger/
