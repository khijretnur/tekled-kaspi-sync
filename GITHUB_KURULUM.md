# Kaspi XML: GitHub kurulumu

Bu klasördeki script her gün Shopify'dan fiyat ve stokları okuyup Kaspi'nin istediği XML dosyasını üretir. GitHub bu dosyayı sabit bir adreste yayınlar, Kaspi de oradan otomatik çeker.

## Kurallar (config.json)

| Ayar | Değer | Anlamı |
|---|---|---|
| company / merchant_id | Tekled by Teksan / Teksan | XML'in başına yazılır |
| locations | Almaty=PP1, Astana=PP2, Atyrau=PP3, Shymkent=PP4, Oskomen=PP5, Aktau=PP6 | Shopify lokasyonu → Kaspi satış noktası |
| min_stock | 10 | Bir noktada stok 10'dan azsa ürün o noktada kapalı gider |
| price_source | compare_at | Üstü çizili fiyat varsa o, yoksa normal fiyat (Zoomia ile aynı) |
| only_listed_skus | true | Sadece `kaspi_skus.txt` içindeki, Kaspi'de zaten olan ürünler gönderilir |

Bir lokasyonun PP kodu boş ya da `PP?` olursa script bilerek çalışmaz. Yanlış eşleşme, stoğun Kaspi'de yanlış şehirde görünmesine yol açar.

## 1. Shopify uygulaması (bir kere)

1. dev.shopify.com → **Create app** → adı: `Kaspi XML`.
2. Yetkiler (Access scopes): `read_products`, `read_inventory`, `read_locations`. Sadece okuma.
3. Uygulamayı `tekled-kz.myshopify.com` mağazasına kurun (Install).
4. **Client ID** ve **Client secret** değerlerini kopyalayın. Bunları kimseyle paylaşmayın, sohbete de yazmayın.

## 2. GitHub deposu

1. github.com'da hesap açın → **New repository** → adı `kaspi-feed`, **Public**.
2. **Add file → Upload files**: şu dosyaları sürükleyin: `kaspi_feed.py`, `config.json`, `kaspi_skus.txt`, `GITHUB_KURULUM.md`.
3. **Add file → Create new file**: dosya adına `.github/workflows/kaspi.yml` yazın, bu klasördeki `kaspi.yml` içeriğini yapıştırın, **Commit**.

## 3. Secrets

Depo → **Settings → Secrets and variables → Actions → New repository secret**:

- `SHOPIFY_CLIENT_ID` = Client ID
- `SHOPIFY_CLIENT_SECRET` = Client secret

## 4. Pages

**Settings → Pages → Source: GitHub Actions**.

## 5. İlk çalıştırma

**Actions → Kaspi XML → Run workflow**. Yeşil tik çıkınca adresler:

- XML: `https://<kullanici-adiniz>.github.io/tekled-kaspi-sync/kaspi.xml`
- Sorun listesi: `https://<kullanici-adiniz>.github.io/tekled-kaspi-sync/audit.csv`

Kırmızı çıkarsa çalıştırmaya tıklayın, `HATA:` ile başlayan satır ne olduğunu söyler.

## 6. Kaspi'ye geçiş

1. İlk XML'i Zoomia'nın son dosyasıyla karşılaştırın (bana gönderebilirsiniz).
2. Doğruysa Kaspi kabineti → **Товары → Загрузить прайс-лист → Автоматическая загрузка** bölümüne XML adresini girin.
3. Ardından Zoomia'dan manuel yüklemeyi bırakın. İkisi birlikte çalışırsa birbirinin üstüne yazar.

## Sonradan değişiklik

`config.json` dosyasını GitHub'da açıp kalem simgesiyle düzenleyin. Bir sonraki çalıştırmada geçerli olur. Zamanlama `kaspi.yml` içindeki `cron` satırındadır.
