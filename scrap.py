from twikit import Client, TooManyRequests
import asyncio
from datetime import datetime
from random import randint
from configparser import ConfigParser
import aiofiles
import aiocsv


MINIMUM_TWEETS = 1000
QUERY = 'makan bergizi gratis OR makan siang gratis OR mbg lang:id'


async def get_tweets_async(client: Client, current_tweets_obj, query_str: str, product_str: str):
    """
    Fungsi asynchronous untuk mendapatkan tweets.
    """
    if current_tweets_obj is None:
        print(f'{datetime.now()} - Getting tweets...')
        new_tweets_obj = await client.search_tweet(query_str, product=product_str)
    else:
        wait_time = randint(5, 10)
        print(f'{datetime.now()} - Getting next tweets after {wait_time} seconds ...')
        await asyncio.sleep(wait_time)
        new_tweets_obj = await current_tweets_obj.next()
    return new_tweets_obj


async def main():
    #* login credentials
    config = ConfigParser()
    config.read('config.ini')
    username = config['X']['username']
    email = config['X']['email']
    password = config['X']['password']

    #* create a csv file and write header asynchronously
    csv_filename = 'tweet_data.csv'
    async with aiofiles.open(csv_filename, mode='w', newline='', encoding='utf-8') as afp:
        writer = aiocsv.AsyncWriter(afp)
        await writer.writerow(['Tweet_count', 'Username', 'Created At', 'Text'])

    #* authenticate to X.com
    client = Client(language='id')

    # # Opsi 1: Login (jika cookies.json tidak ada atau tidak valid)
    # print(f'{datetime.now()} - Attempting login...')
    # try:
    #     # Jika client.login adalah coroutine, await langsung
    #     await client.login(auth_info_1=username, auth_info_2=email, password=password)
    #     print(f'{datetime.now()} - Login successful')
    #     # Opsional: Simpan cookies setelah login berhasil jika Anda ingin menggunakannya nanti
    #     await asyncio.to_thread(client.save_cookies, 'cookies.json')
    #     print(f'{datetime.now()} - Cookies saved to cookies.json')
    # except Exception as e:
    #     print(f'{datetime.now()} - Login failed: {e}')
    #     return # Keluar jika login gagal

    # Opsi 2: Load cookies (lebih disarankan untuk penggunaan berulang)
    try:
        print(f'{datetime.now()} - Loading cookies...')
        await asyncio.to_thread(client.load_cookies, 'cookies.json')
        print(f'{datetime.now()} - Cookies loaded successfully.')
    except FileNotFoundError:
        print(f'{datetime.now()} - cookies.json not found. Please login first or ensure the file exists.')
        print(f'{datetime.now()} - Tip: Uncomment login block and run once to generate cookies.json')
        return # Keluar jika cookies tidak ditemukan

    tweet_count = 0
    tweets_obj = None # Ini akan menjadi objek hasil dari search_tweet atau next()

    while tweet_count < MINIMUM_TWEETS:
        try:
            tweets_obj = await get_tweets_async(client, tweets_obj, QUERY, 'Latest')
        except TooManyRequests as e:
            # rate_limit_reset_dt = datetime.fromtimestamp(e.rate_limit_reset) # e.rate_limit_reset mungkin tidak ada di semua versi/kasus
            # print(f'{datetime.now()} - Rate limit reached. Waiting until {rate_limit_reset_dt}')
            # wait_duration = rate_limit_reset_dt - datetime.now()
            # if wait_duration.total_seconds() > 0:
            #     await asyncio.sleep(wait_duration.total_seconds())
            # Untuk amannya, tunggu waktu standar jika detail reset tidak tersedia
            wait_for = getattr(e, 'rate_limit_reset', None)
            if wait_for:
                rate_limit_reset_dt = datetime.fromtimestamp(wait_for)
                print(f'{datetime.now()} - Rate limit reached. Waiting until {rate_limit_reset_dt}')
                wait_duration = rate_limit_reset_dt - datetime.now()
                if wait_duration.total_seconds() > 0:
                    await asyncio.sleep(wait_duration.total_seconds())
                else: # Waktu reset sudah lewat, coba lagi setelah jeda singkat
                    await asyncio.sleep(randint(60, 120))
            else: # Jika tidak ada info rate_limit_reset
                print(f'{datetime.now()} - Rate limit reached. Waiting for a default period (e.g., 15 mins).')
                await asyncio.sleep(15 * 60) # Tunggu 15 menit sebagai default
            continue
        except Exception as e: # Menangkap exception lain yang mungkin terjadi dari twikit
            print(f'{datetime.now()} - An unexpected error occurred: {e}')
            print(f'{datetime.now()} - Retrying after a short delay...')
            await asyncio.sleep(randint(10, 20)) # Jeda sebelum mencoba lagi
            tweets_obj = None # Reset untuk mencoba pencarian baru
            continue


        if not tweets_obj: # Jika tweets_obj adalah None atau kosong setelah pemanggilan
            print(f'{datetime.now()} - No more tweets found or error in fetching.')
            break

        current_batch_tweets = []
        try:
            for tweet in tweets_obj:
                current_batch_tweets.append(tweet)

            if not current_batch_tweets:
                print(f'{datetime.now()} - No tweets in the current batch. End of search might be reached.')
                break

        except TypeError as te: # Jika tweets_obj tidak iterable/async iterable
            print(f'{datetime.now()} - tweets_obj is not (async) iterable: {te}. Possibly an error or end of data.')
            # Cek apakah ini karena tidak ada tweet lagi atau error
            # Untuk beberapa API, objek "next" mungkin None jika tidak ada lagi data
            if tweets_obj is None:
                 print(f'{datetime.now()} - Confirmed no more tweets or error led to None object.')
                 break
            await asyncio.sleep(5) # Jeda singkat
            tweets_obj = None # Reset untuk mencoba search ulang jika ini adalah error sementara
            continue
        except Exception as ex_iter: # Menangkap error lain saat iterasi
            print(f'{datetime.now()} - Error during iteration of tweets: {ex_iter}')
            await asyncio.sleep(randint(5,15))
            tweets_obj = None # Reset
            continue


        async with aiofiles.open(csv_filename, mode='a', newline='', encoding='utf-8') as afp:
            writer = aiocsv.AsyncWriter(afp)
            for tweet in current_batch_tweets:
                tweet_count += 1
                tweet_data = [
                    tweet_count,
                    tweet.user.name,
                    tweet.created_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(tweet.created_at, datetime) else tweet.created_at,
                    tweet.text.replace('\n', ' ').replace('\r', ' ') # Ganti newline & carriage return
                ]
                await writer.writerow(tweet_data)
                if tweet_count >= MINIMUM_TWEETS:
                    break
        
        print(f'{datetime.now()} - Processed up to {tweet_count} tweets')
        if tweet_count >= MINIMUM_TWEETS:
            break

    print(f'{datetime.now()} - Done! Got {tweet_count} tweets found')

if __name__ == "__main__":
    # Membuat file config.ini dummy jika belum ada untuk pengujian
    # Anda harus menggantinya dengan kredensial asli Anda
    try:
        with open('config.ini', 'r') as f:
            pass
    except FileNotFoundError:
        print("config.ini not found, creating a dummy one. PLEASE EDIT IT with your credentials.")
        dummy_config = ConfigParser()
        dummy_config['X'] = {
            'username': 'YOUR_X_USERNAME',
            'email': 'YOUR_X_EMAIL_ASSOCIATED_WITH_ACCOUNT',
            'password': 'YOUR_X_PASSWORD'
        }
        with open('config.ini', 'w') as configfile:
            dummy_config.write(configfile)
        print("Dummy config.ini created. Please edit it and then re-run the script.")
        exit()

    asyncio.run(main())