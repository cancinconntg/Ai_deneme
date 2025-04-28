# Telegram Geçmiş Analiz Botu

Bu bot, Pyrogram (kullanıcı hesabı olarak) ve Gemini AI kullanarak Telegram sohbetlerinin geçmişini analiz eder, özetler ve bu geçmiş hakkında sorular sormanızı sağlar. Bot sadece sizin tarafınızdan (belirttiğiniz `ADMIN_ID` ile) kullanılabilir.

## Özellikler

* Belirtilen sohbetin son N mesajını çeker.
* Sohbet geçmişini Google Gemini AI kullanarak özetler veya hakkında sorular sorar.
* String Session kullanarak kullanıcı hesabı ile çalışır (sürekli giriş gerektirmez).
* Sadece belirlenen admin kullanıcısının komutlarını kabul eder.
* Sohbet geçmişinin tam JSON dökümünü admin'e gönderir.
* `/ping`, `/list`, `/id` gibi yardımcı komutlar içerir.

## Heroku ile Dağıtım

Bu botu kolayca Heroku üzerinde çalıştırabilirsiniz:

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/xxxx/xxxx)

**Adımlar:**

1.  Yukarıdaki "Deploy to Heroku" düğmesine tıklayın.
2.  Henüz giriş yapmadıysanız Heroku hesabınıza giriş yapın.
3.  Uygulama için bir isim seçin (isteğe bağlı).
4.  **"Config Vars"** bölümünde istenen tüm ortam değişkenlerini doldurun. Bu değişkenlerin açıklamaları aşağıdadır. **`TG_STRING_SESSION`** değerini nasıl alacağınız bir sonraki bölümde açıklanmıştır.
5.  **"Deploy app"** düğmesine tıklayın.
6.  Dağıtım tamamlandıktan sonra, Heroku kontrol panelindeki "Resources" sekmesinden `worker` dyno'sunun açık olduğundan emin olun. Gerekirse yanındaki kalem ikonuna tıklayıp "on" konumuna getirin ve "Confirm" deyin.
7.  Botun durumunu ve olası hataları görmek için Heroku kontrol panelindeki "View logs" seçeneğini kullanın.

### `TG_STRING_SESSION` Nasıl Oluşturulur?

`TG_STRING_SESSION`, Pyrogram'ın hesabınıza programatik olarak giriş yapabilmesi için gereken özel bir anahtardır. Bunu elde etmek için:

1.  Bu depodaki `generate_session.py` betiğini bilgisayarınıza indirin.
2.  Bilgisayarınızda Python ve Pyrogram'ın kurulu olduğundan emin olun:
    ```bash
    pip install pyrogram TgCrypto
    ```
3.  Terminal veya komut istemcisini açın ve betiğin olduğu dizine gidin.
4.  Betiği çalıştırın:
    ```bash
    python generate_session.py
    ```
5.  Betik sizden `API ID`, `API Hash` (my.telegram.org'dan alınır) ve Telegram'a kayıtlı telefon numaranızı isteyecektir.
6.  Telefonunuza gelen Telegram kodunu girin.
7.  Giriş başarılı olursa, betik size uzun bir karakter dizisi olan **String Session**'ı verecektir.
8.  Bu **String Session** değerini kopyalayın ve Heroku'daki `TG_STRING_SESSION` ortam değişkenine yapıştırın.
9.  **Bu String Session değerini ASLA kimseyle paylaşmayın! Hesabınıza tam erişim sağlar.**

### Yapılandırma Değişkenleri (Config Vars)

Heroku'da ayarlamanız gereken ortam değişkenleri:

* `ADMIN_ID`: Botun komutlarını kullanabilecek Telegram kullanıcısının unique ID'si. Birçok bot (örn: @userinfobot) ID'nizi size söyleyebilir.
* `TG_API_ID`: [my.telegram.org](https://my.telegram.org/apps) adresinden alınan API ID.
* `TG_API_HASH`: [my.telegram.org](https://my.telegram.org/apps) adresinden alınan API Hash.
* `TG_BOT_TOKEN`: Telegram [@BotFather](https://t.me/BotFather)'dan alınan bot token'ı.
* `AI_API_KEY`: [Google AI Studio](https://makersuite.google.com/app/apikey) üzerinden alınan Gemini API Anahtarı.
* `TG_STRING_SESSION`: Yukarıdaki adımlarla oluşturulan Pyrogram String Session.

## Kullanım

Botu başlattıktan sonra (ve admin olarak tanımlandıktan sonra) aşağıdaki şekillerde kullanabilirsiniz:

* **Sohbet Geçmişi Analizi:** Bota aşağıdaki formatta bir mesaj gönderin:
    ```
    <sohbet_id_veya_kullaniciadi>
    <mesaj_sayisi (isteğe bağlı, varsayılan 20)>
    <AI için soru/istem (isteğe bağlı, varsayılan özetleme)>
    ```
    Örnek:
    ```
    @bir_kanal_adi
    50
    Bu kanaldaki son tartışmaların ana başlıkları nelerdi?
    ```
    veya sadece ID ile:
    ```
    -1001234567890
    100
    ```
    (Bu durumda varsayılan istem olan özetleme kullanılır.)

* **/list `<limit>` `<tür>`**: Son sohbetleri listeler. Örn: `/list 15 grup` (son 15 grubu listeler), `/list 5 özel` (son 5 özel sohbeti listeler). Tür belirtilmezse tüm türler, limit belirtilmezse 10 sohbet listelenir.
* **/ping**: Botun ve bağlı servislerin (Pyrogram, Gemini) durumunu kontrol eder.
* **/ai `<sorgu>`**: Doğrudan Gemini AI'ye soru sorar. Bu komut sohbet geçmişi bağlamını kullanmaz, ancak önceki `/ai` komutlarıyla bir diyalog geçmişi tutar.
* **/ai_clean**: `/ai` komutları ile oluşan diyalog geçmişini temizler.
* **/id**: Yanıtladığınız mesajın ID'sini ve gönderen bilgilerini verir.
* **/json**: Örnek bir JSON dosyası gönderir (test amaçlı).

