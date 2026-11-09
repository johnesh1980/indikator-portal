# SSV hisobot tekshiruvchi

DMED orqali qabul qilingan SSV statistik hisobotlarini (`.xlsm`) mantiqiy nazoratlar bo'yicha
avtomatik tekshiradigan Windows dasturi. Fayllardagi makrosga bog'liq emas: raqamlar hisobotning
yashirin `Tabl` varag'idan o'qiladi, nazoratlar esa markaziy `nazoratlar.xlsx` faylidan olinadi.

## Foydalanish

1. `SSV_Tekshiruvchi.exe` ni alohida papkaga qo'ying (masalan `D:\SSV_Tekshiruvchi\`) va ishga tushiring.
2. **1. Hisobotlar papkasi** — DMED dan yuklangan `.xlsm` fayllar turgan papkani tanlang
   (ichki papkalar ham ko'riladi).
3. **2. Ma'lumotnomalar** — birinchi marta **Reyestr → Yangilash…** orqali DMED reyestrini (`.xls`) tanlang.
   Nazoratlar fayli dastur bilan birga keladi.
4. **Tekshirishni boshlash** — natija `Natijalar\Natija_<sana>.xlsx` fayliga yoziladi.

Dastur yonida ikkita papka paydo bo'ladi:

| Papka | Ichida |
|---|---|
| `malumotnomalar\` | joriy `nazoratlar.xlsx`, `reyestr.xls`, `arxiv\` (eski versiyalar), `sozlamalar.json` |
| `Natijalar\` | har bir tekshiruv natijasi |

### Natija.xlsx varaqlari

| Varaq | Mazmuni |
|---|---|
| Xulosa | har bir fayl: shakl, STIR, muassasa, holat, xatolar soni, fayl makrosining javobi, reyestrda bormi |
| Xatolar | har bir buzilgan nazorat: bo'lim, satr/ustun, chap va o'ng qiymat, farq |
| Eng ko'p xatolar | qaysi nazorat necha marta buzilgan |
| Topshirmaganlar | reyestr bo'yicha shu shaklni topshirishi kerak bo'lgan, lekin papkada fayli yo'q muassasalar |
| Ma'lumot | umumiy sonlar, vaqt |

"Taqqoslash" ustunida fayl makrosi "jo'natish mumkin" degan, lekin dastur xato topgan hollar ko'rsatiladi.

## Nazoratlarni o'zgartirish

`nazoratlar.xlsx` ni Excelda oching, o'zgartiring, so'ng dasturda **Mantiqiy nazoratlar → Yangilash…**
orqali tanlang. Dastur faylni tekshiradi, joriy versiya bilan farqini ko'rsatadi va eski versiyani arxivga oladi.
**Versiyalar tarixi** dan istalgan oldingi versiyaga qaytish mumkin.

`Nazoratlar` varag'i ustunlari: `Forma`, `Bo'lim`, `Xato kodi`, `Shifr`, `Ustun dan`, `Ustun gacha`,
`Darajasi` (`Xato`/`Ogohlantirish`), `Faol` (`Ha`/`Yo'q`), `Izoh`.

Shifr — SSV shakllaridagi `textlog` bilan bir xil yozuv:

```
<shart><ayirish><tur>:<kod1>:<kod2>:...:
=0R:19:1:2:3:     19-satr = 1 + 2 + 3-satrlar (Ustun dan..gacha oralig'idagi har bir ustunda)
>0C:1:2:          1-ustun ≥ 2-ustun (bo'limning har bir satrida)
=1C:4:1:2:3:      4-ustun = 1 + 2 − 3-ustunlar (oxirgi 1 ta had ayiriladi)
=0N:237:238:      237 va 238-satrlar = 0
```

> Excelda `=` bilan boshlanadigan matnni yozganda oldiga apostrof qo'ying: `'=0R:1:2:3:` —
> aks holda Excel uni formula deb tushunadi.

`Formalar` varag'ida har bir shakl uchun `Tabl oralig'i` va `To'liqlik sharti` (makrosdagi
"ma'lumot kiritilganmi" sharti, masalan `D("1.0","26.0",1) > 0`) turadi.

## Nazoratlar faylini shablonlardan qayta yasash

Yangi shablonlar (bo'sh SSV `.xlsm` fayllari) kelganda:

```
pip install -r requirements.txt
python build_rules.py <shablonlar_papkasi> -o nazoratlar.xlsx
```

Skript har bir shablondan makrosni (VBA) va `textlog` ni o'qiydi, eski/yangi makros yozuvlarini bitta
ko'rinishga keltiradi va shablondagi xatolarni `Izoh` ustuniga yozadi (xatoli nazoratlar `Faol = Yo'q`).
Haqiqiy hisobotlar bilan aniqlangan tuzatishlar `build_rules.py` dagi `OVERRIDES` ro'yxatida.

## Buyruq qatoridan tekshirish

```
python checker.py <hisobotlar_papkasi> -n nazoratlar.xlsx -r reyestr.xls -o Natija.xlsx
```

## .exe yig'ish

`ssv_tekshiruvchi/` dagi o'zgarish GitHub'ga yuborilganda `.github/workflows/ssv-tekshiruvchi-exe.yml`
Windows'da testlarni ishga tushiradi va `SSV_Tekshiruvchi.exe` ni yig'adi (Actions → artifact).
Qo'lda Windows'da:

```
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name SSV_Tekshiruvchi --add-data "nazoratlar.xlsx;." app.py
```
