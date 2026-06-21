# Ilmavalvontaselostesovellus

Tämä on ilmavalvontaselosteiden kirjaus- ja visualisointityökalu. Sovellus mahdollistaa ilmamaalien raportoinnin, karttanäkymän piirtämisen MGRS-ruudukon mukaan sekä varoitus- ja hälytyskehien käytön oman sijainnin ympärillä. Raportteja voi syöttää käsin lomakkeella, tai ne voivat tulla automaattisesti puheentunnistuksen kautta (esim. FM-radiolähetteen ilmavalvontaselosteesta).

---

## 🔧 Ominaisuudet

- ✏️ Lisää raportteja ilmamaaleista (MGRS, suunta, nopeus, korkeus, lukumäärä, lisätiedot)
- 🗺️ Näytä maalit kartalla kompassisuunnan ja sijainnin mukaan
- 🧭 Määritä oma sijainti (MGRS) ja keskitä kartta siihen
- 📏 Määritä kartan halkaisija (km)
- 🟠 Oranssi varoituskehä ja 🔴 punainen hälytyskehä piirretään kartalle
- ⚠️ Popup-hälytys, kun maali tulee kehien sisään
- 📊 Raporttitaulukko, josta voi poistaa yksittäisiä raportteja
- ➕ Useiden raporttien välinen lentorata yhdistetään kaarella
- 🎙️ Automaattinen raportointi puheesta: mikrofoni → Whisper-puheentunnistus → jäsennys → kartta/taulukko päivittyy itsestään
- 🎚️ Äänilähteen valinta ja VU-mittari sivulla
- ▶️/⏹️ Kuuntelun käynnistys/pysäytys sivulta, tilan/sykkeen ilmaisin
- 🐞 Debug-näkymä, joka näyttää raa'an tunnistetun puheen riippumatta siitä, jäsentyikö se raportiksi
- 🗑️ "Tyhjennä tietokanta" -nappi

---

## 📁 Tiedostot

| Tiedosto             | Kuvaus                                                              |
|-----------------------|----------------------------------------------------------------------|
| `index.html`          | Käyttöliittymä ja lomakkeet                                         |
| `app.js`              | Sovelluksen logiikka, piirto ja puheraporttien vastaanotto (polling) |
| `style.css`           | Tyylit                                                              |
| `server.py`           | Paikallinen HTTP-palvelin (vain `127.0.0.1`): tarjoaa staattiset tiedostot, `reports.json`-rajapinnan sekä puheputken käynnistys/pysäytys-rajapinnan |
| `live_pipeline.py`    | Jatkuva äänenkäsittely: mikrofoni → Whisper (VAD) → jäsennys → raportin lähetys palvelimelle. Kirjoittaa myös `devices.json`, `level.json` (VU-mittari) ja `transcripts.json` (debug) |
| `parser.py`           | Jäsentää puheentunnistuksen tekstin rakenteelliseksi raportiksi (ks. raporttimuoto alla) |
| `install.sh`          | Asennusskripti: järjestelmäriippuvuudet, whisper.cpp + mallit, äänioikeudet, systemd-palvelu |

Ajonaikaisesti syntyvät tiedostot (`reports.json`, `config.json`, `devices.json`, `level.json`, `transcripts.json`) eivät kuulu versionhallintaan.

---

## 🚀 Käyttöönotto

Vaatii Linux-koneen, jossa on PipeWire-äänijärjestelmä (esim. tuore Ubuntu/Debian-työpöytä) ja mikrofoni. Whisper.cpp käännetään paikallisesti, joten suorittimen AVX2-tuki nopeuttaa puheentunnistusta merkittävästi.

```bash
git clone https://github.com/kayttaja/ilmavalvontaseloste.git
cd ilmavalvontaseloste
./install.sh
```

`install.sh` tekee seuraavat (ja sen voi ajaa uudelleen turvallisesti, jos jokin vaihe on jo tehty):

1. Asentaa järjestelmäpaketit (build-essential, cmake, ffmpeg, PipeWire/WirePlumber, python3)
2. Lisää käyttäjän `audio`-ryhmään (mikrofonin käyttöoikeus)
3. Ottaa käyttöön systemd-lingeringin (palvelin pysyy käynnissä uloskirjautumisen jälkeen)
4. Kloonaa ja kääntää [whisper.cpp](https://github.com/ggerganov/whisper.cpp):n, lataa `small`-puheentunnistusmallin ja Silero VAD -mallin
5. Asentaa ja käynnistää systemd-käyttäjäpalvelun (`ilmavalvontaseloste.service`), joka pyörittää `server.py`:tä

Asennuksen jälkeen sovellus on osoitteessa **http://127.0.0.1:8642/** (vain paikallinen kone — ei verkkoon näkyvä).

> **Huom:** jos käyttäjä lisättiin `audio`-ryhmään juuri asennuksessa, kirjaudu ulos ja sisään (tai käynnistä kone uudelleen) ennen kuin mikrofoni toimii.

Puheentunnistuksen kuuntelu **ei** käynnisty automaattisesti palvelimen kanssa — se käynnistetään/pysäytetään sivun "Äänilähde"-osiosta löytyvällä napilla.

### Ylläpito

```bash
git pull
systemctl --user restart ilmavalvontaseloste
```

Tila ja lokit:

```bash
systemctl --user status ilmavalvontaseloste
journalctl --user -u ilmavalvontaseloste -f
```

---

## 🎙️ Puheentunnistuksen raporttimuoto

Selosteen rakenteellinen järjestys on aina sama (herätyssana, jonka jälkeen kentät tässä järjestyksessä):

| Kenttä | Muoto |
|---|---|
| Herätyssana | "uusi maali" tai "maali" |
| Maalin numero | aina neljä numeroa |
| Sijainti | MGRS, 10×10 km ruutu (2 kirjainta + 2 numeroa, esim. "Mike Hotel 5 5" → MH55) |
| Suunta | ilmansuuntasana + asteet (esim. "koilliseen 0 3 0") |
| Nopeus | Hidas / Nopea / Erittäin nopea |
| Korkeus | Pinnassa / Matalalla / Korkealla |
| Lukumäärä | Yksittäinen / Pari / Useita (+ tarkka lukumäärä mikäli mainittu) |
| Muodostelma | vapaa teksti |
| Muut tiedot | vapaa teksti, voi puuttua kokonaan |

`parser.py` tunnistaa kentät ankkurisanoilla ja sallii pienen epätarkkuuden (esim. "maik" → "mike") puheentunnistuksen virheiden vuoksi. Ainoastaan sijainti (MGRS) vaaditaan ennen kuin raportti lähetetään sovellukseen — puuttuva tai osittainen tieto näytetään silti, sillä virheellinenkin maali halutaan näkyviin mieluummin kuin että tieto hiljaa hylätään.
