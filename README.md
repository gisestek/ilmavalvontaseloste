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
- 🧠 Whisper-mallin valinta sivulta + suorituskykymittari, joka varoittaa jos valittu malli on laitteelle liian raskas

---

## 💻 Laitteistovaatimukset

Puheentunnistus on huomattavasti raskain osa sovellusta — selain ja kartta toimivat kevyestikin millä tahansa koneella, mutta Whisper-puheentunnistus on prosessoririippuvainen.

**Ehdottomat vaatimukset:**
- Linux PipeWire-äänijärjestelmällä (esim. tuore Ubuntu/Debian-työpöytä). `pw-record`/`wpctl` täytyy löytyä.
- 64-bit x86 (AMD64) -suoritin. **AVX2-tuki on käytännössä pakollinen** — sitä vanhemmilla suorittimilla (esim. 2010-luvun alun mobiiliprosessorit) puheentunnistus on jopa 25–50x hitaampaa, eikä reaaliaikainen kuuntelu ole käytännössä mahdollista millään mallilla.
- Vähintään ~1 GB vapaata RAM-muistia `small`-mallille, enemmän isommille malleille (ks. taulukko alla).

**Mitatut suorituskykytulokset** (29 s ääninäyte, `whisper.cpp`):

| Kone | Mallit | Tulos |
|---|---|---|
| 2010-luvun mobiili-i5 (ei AVX2), 1 ydin | `base` | ~280 s → **2.4x hitaampi kuin reaaliaika** ❌ |
| 2010-luvun mobiili-i5 (ei AVX2), 4 ydintä | `base` | 71 s → **2.4x hitaampi kuin reaaliaika** ❌ |
| Moderni 8-ydin (AVX2), `base` | `base` | 2.3 s → **12.6x nopeampi kuin reaaliaika** ✅ |
| Moderni 8-ydin (AVX2), `small` | `small` | 7.2 s → **4x nopeampi kuin reaaliaika** ✅ |
| Moderni 8-ydin (AVX2), `large-v3` | `large-v3` | 42 s → **1.4x hitaampi kuin reaaliaika** ⚠️ |

Johtopäätös: **AVX2-tuki ratkaisee enemmän kuin ydinmäärä.** Ydinmäärän kasvattaminen ei skaalaa lineaarisesti (4 ydintä ≈ 1.7x nopeutus, ei 4x), mutta AVX2-tuettu moderni suoritin on kertaluokkaa nopeampi samalla ydinmäärällä.

### Minkä mallin pitäisi valita?

Malli valitaan ajonaikaisesti sivun "Äänilähde"-osiosta, ei asennusvaiheessa — `install.sh` lataa oletuksena `tiny`, `base` ja `small` mallit valmiiksi, joten niiden välillä voi kokeilla ja vaihtaa ilman uudelleenasennusta.

- **`small` on suositeltu oletus** modernille (AVX2) koneelle: hyvä tarkkuus, paljon reaaliaikamarginaalia.
- **`base`** jos haluat enemmän marginaalia (esim. ajat samalla muita raskaita prosesseja koneella) — tarkkuus hieman heikompi mutta yhä käyttökelpoinen.
- **`tiny`** vain hyvin heikolle laitteistolle tai nopeaan testaukseen — numerot/koodisanat menevät usein väärin, ei suositella tuotantokäyttöön.
- **`large-v3`** parhaaseen tarkkuuteen, mutta ei reaaliaikainen tavallisella kannettavalla (~1.4x hitaampi kuin reaaliaika) — hyvä esim. jälkikäteen tarkistettavaan offline-litterointiin, ei jatkuvaan kuunteluun. Vaatii myös ~4 GB RAM-muistia mallin lataamiseen.

**Miten tiedän, että malli on liian raskas?** Sivun "Äänilähde"-osiossa näkyy malliarvioinnin alla suorituskykymittari ("Tunnistusviive: X s / Y s ikkuna"). Jos viive ylittää ikkunan pituuden (oletuksena 10 s), mittari muuttuu punaiseksi ja varoittaa — se tarkoittaa, että puheentunnistus jää jatkuvasti jälkeen todellisesta puheesta, ja malli kannattaa vaihtaa pienempään.

---

## 📁 Tiedostot

| Tiedosto             | Kuvaus                                                              |
|-----------------------|----------------------------------------------------------------------|
| `index.html`          | Käyttöliittymä ja lomakkeet                                         |
| `app.js`              | Sovelluksen logiikka, piirto ja puheraporttien vastaanotto (polling) |
| `style.css`           | Tyylit                                                              |
| `server.py`           | Paikallinen HTTP-palvelin (vain `127.0.0.1`): tarjoaa staattiset tiedostot, `reports.json`-rajapinnan sekä puheputken käynnistys/pysäytys-rajapinnan |
| `live_pipeline.py`    | Jatkuva äänenkäsittely: mikrofoni → Whisper (VAD) → jäsennys → raportin lähetys palvelimelle. Kirjoittaa myös `devices.json`, `models.json`, `level.json` (VU-mittari), `perf.json` (suorituskykymittari) ja `transcripts.json` (debug) |
| `parser.py`           | Jäsentää puheentunnistuksen tekstin rakenteelliseksi raportiksi (ks. raporttimuoto alla) |
| `install.sh`          | Asennusskripti: järjestelmäriippuvuudet, whisper.cpp + mallit, äänioikeudet, systemd-palvelu |

Ajonaikaisesti syntyvät tiedostot (`reports.json`, `config.json`, `devices.json`, `models.json`, `level.json`, `perf.json`, `transcripts.json`) eivät kuulu versionhallintaan.

---

## 🚀 Käyttöönotto

Vaatii Linux-koneen, jossa on PipeWire-äänijärjestelmä (esim. tuore Ubuntu/Debian-työpöytä) ja mikrofoni. Whisper.cpp käännetään paikallisesti, joten suorittimen AVX2-tuki nopeuttaa puheentunnistusta merkittävästi.

```bash
git clone https://github.com/gisestek/ilmavalvontaseloste.git
cd ilmavalvontaseloste
./install.sh
```

`install.sh` tekee seuraavat (ja sen voi ajaa uudelleen turvallisesti, jos jokin vaihe on jo tehty):

1. Asentaa järjestelmäpaketit (build-essential, cmake, ffmpeg, PipeWire/WirePlumber, python3)
2. Lisää käyttäjän `audio`-ryhmään (mikrofonin käyttöoikeus)
3. Ottaa käyttöön systemd-lingeringin (palvelin pysyy käynnissä uloskirjautumisen jälkeen)
4. Kloonaa ja kääntää [whisper.cpp](https://github.com/ggerganov/whisper.cpp):n, lataa `tiny`/`base`/`small`-puheentunnistusmallit ja Silero VAD -mallin (mallia voi vaihtaa jälkikäteen sivulta, ks. "Laitteistovaatimukset" yllä)
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
