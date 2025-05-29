# Ilmavalvontaselostesovellus

Tämä on selainpohjainen ilmavalvontaselosteiden kirjaus- ja visualisointityökalu. Sovellus mahdollistaa ilmamaalien raportoinnin, karttanäkymän piirtämisen MGRS-ruudukon mukaan sekä varoitus- ja hälytyskehien käytön oman sijainnin ympärillä.

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

---

## 📁 Tiedostot

| Tiedosto       | Kuvaus                            |
|----------------|-----------------------------------|
| `index.html`   | Käyttöliittymä ja lomakkeet       |
| `app.js`       | Sovelluksen logiikka ja piirto    |
| `style.css`    | (valinnainen, tyylit voivat olla myös suoraan HTML:ssä) |

---

## 🚀 Käyttöönotto

1. Lataa tai kloonaa tämä repositorio:
   ```bash
   git clone https://github.com/kayttaja/ilmavalvontaseloste.git
