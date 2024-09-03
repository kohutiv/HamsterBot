import heapq
import asyncio
from pprint import pprint
from time import time
from random import randint, shuffle
from datetime import datetime, timedelta

import aiohttp
import aiohttp_proxy
from pyrogram import Client

from bot.config import settings
from bot.utils.logger import logger, countdown_timer
from bot.utils.proxy import check_proxy
from bot.utils.tg_web_data import get_tg_web_data
from bot.utils.scripts import decode_cipher, get_headers, get_mini_game_cipher, get_promo_code
from bot.exceptions import InvalidSession

from bot.api.auth import login
from bot.api.clicker import (
    get_version_config,
    get_game_config,
    get_profile_data,
    get_ip_info,
    get_account_info,
    get_skins,
    send_taps, buy_skin, select_skin)
from bot.api.boosts import get_boosts, apply_boost
from bot.api.upgrades import get_upgrades, buy_upgrade
from bot.api.combo import claim_daily_combo, get_combo_cards
from bot.api.cipher import claim_daily_cipher
from bot.api.promo import get_apps_info, get_promos, apply_promo
from bot.api.minigame import start_daily_mini_game, claim_daily_mini_game
from bot.api.tasks import get_tasks, get_airdrop_tasks, check_task
from bot.api.exchange import select_exchange
from bot.api.nuxt import get_nuxt_builds


class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client

    async def run(self, proxy: str | None) -> None:
        global is_claimed
        access_token_created_time = 0

        if settings.USE_RANDOM_DELAY_IN_RUN:
            random_delay = randint(settings.RANDOM_DELAY_IN_RUN[0], settings.RANDOM_DELAY_IN_RUN[1])
            logger.info(f"{self.tg_client.name} | Run for <lw>{random_delay}s</lw>")

            await asyncio.sleep(delay=random_delay)

        headers = get_headers(name=self.tg_client.name)
        proxy_conn = aiohttp_proxy.ProxyConnector().from_url(proxy) if proxy else None

        http_client = aiohttp.ClientSession(headers=headers, connector=proxy_conn)

        if proxy:
            await check_proxy(http_client=http_client, proxy=proxy, session_name=self.session_name)

        tg_web_data = await get_tg_web_data(tg_client=self.tg_client, proxy=proxy, session_name=self.session_name)

        if not tg_web_data:
            if not http_client.closed:
                await http_client.close()
            if proxy_conn:
                if not proxy_conn.closed:
                    proxy_conn.close()

            return

        while True:
            try:
                if http_client.closed:
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    proxy_conn = aiohttp_proxy.ProxyConnector().from_url(proxy) if proxy else None
                    http_client = aiohttp.ClientSession(headers=headers, connector=proxy_conn)

                if time() - access_token_created_time >= 10000:
                    http_client.headers.pop('Authorization', None)

                    await get_nuxt_builds(http_client=http_client)

                    access_token = await login(
                        http_client=http_client,
                        tg_web_data=tg_web_data,
                        session_name=self.session_name,
                    )

                    if not access_token:
                        continue

                    http_client.headers['Authorization'] = f"Bearer {access_token}"

                    access_token_created_time = time()

                    account_info = await get_account_info(http_client=http_client)
                    user_id = account_info.get('accountInfo', {}).get('id', 1)

                    profile_data = await get_profile_data(http_client=http_client)

                    config_version = http_client.headers.get('Config-Version')
                    http_client.headers.pop('Config-Version', None)
                    if config_version:
                        version_config = await get_version_config(http_client=http_client,
                                                                  config_version=config_version)

                    game_config = await get_game_config(http_client=http_client)
                    upgrades_data = await get_upgrades(http_client=http_client)
                    tasks = await get_tasks(http_client=http_client)
                    airdrop_tasks = await get_airdrop_tasks(http_client=http_client)
                    ip_info = await get_ip_info(http_client=http_client)
                    skins = await get_skins(http_client=http_client)

                    ip = ip_info.get('ip', 'NO')
                    country_code = ip_info.get('country_code', 'NO')
                    city_name = ip_info.get('city_name', 'NO')
                    asn_org = ip_info.get('asn_org', 'NO')

                    logger.info(f"{self.session_name} | IP: <lw>{ip}</lw> | Country: <le>{country_code}</le> | "
                                f"City: <lc>{city_name}</lc> | Network Provider: <lg>{asn_org}</lg>")

                    last_passive_earn = int(profile_data.get('lastPassiveEarn', 0))
                    earn_on_hour = int(profile_data.get('earnPassivePerHour', 0))
                    total_keys = profile_data.get('totalKeys', 0)
                    balance = int(profile_data.get('balanceCoins', 0))
                    total = int(profile_data.get('totalCoins', 0))
                    logger.info(f"{self.session_name} | Total balance: <lg>+{balance:,}</lg> | "
                                f"Balance to save: <ly>{settings.BALANCE_TO_SAVE:,}</ly> | "
                                f"Total: <ly>{total:,}</ly>")

                    logger.info(f"{self.session_name} | Last passive earn: <lg>+{last_passive_earn:,}</lg> | "
                                f"Earn every hour: <ly>{earn_on_hour:,}</ly> | Total keys: <le>{total_keys}</le>")

                    available_energy = profile_data.get('availableTaps', 0)

                    upgrades = upgrades_data['upgradesForBuy']
                    daily_combo = upgrades_data.get('dailyCombo')
                    if daily_combo and settings.APPLY_COMBO and datetime.now().hour >= settings.WAKE_UP:
                        bonus = daily_combo['bonusCoins']
                        is_claimed = daily_combo['isClaimed']
                        upgraded_list = daily_combo['upgradeIds']

                        if not is_claimed:
                            combo_cards = await get_combo_cards(http_client=http_client)

                            cards = combo_cards['combo']
                            date = combo_cards['date']

                            available_combo_cards = [
                                data for data in upgrades
                                if data['isAvailable'] is True
                                   and data['id'] in cards
                                   and data['id'] not in upgraded_list
                                   and data['isExpired'] is False
                                   and data.get('cooldownSeconds', 0) == 0
                                   and data.get('maxLevel', data['level']) >= data['level']
                            ]

                            start_bonus_round = datetime.strptime(date, "%d-%m-%y").replace(hour=15)
                            end_bonus_round = start_bonus_round + timedelta(days=1)

                            if start_bonus_round <= datetime.now() < end_bonus_round:
                                common_price = sum([upgrade['price'] for upgrade in available_combo_cards])
                                need_cards_count = 3 - len(upgraded_list)
                                possible_cards_count = len(available_combo_cards)
                                is_combo_accessible = need_cards_count == possible_cards_count

                                if not is_combo_accessible:
                                    logger.info(f"{self.session_name} | "
                                                f"<lr>Daily combo is not applicable</lr>, you can only purchase {possible_cards_count} of {need_cards_count} cards")

                                if balance < common_price:
                                    logger.info(f"{self.session_name} | "
                                                f"<lr>Daily combo is not applicable</lr>, you don't have enough coins. Need <ly>{common_price:,}</ly> coins, but your balance is <lr>{balance:,}</lr> coins")

                                if common_price < settings.MAX_COMBO_PRICE and balance > common_price and is_combo_accessible:
                                    for upgrade in available_combo_cards:
                                        upgrade_id = upgrade['id']
                                        level = upgrade['level']
                                        price = upgrade['price']
                                        profit = upgrade['profitPerHourDelta']

                                        logger.info(f"{self.session_name} | "
                                                    f"Sleep <lw>5s</lw> before upgrade <lr>combo</lr> card <le>{upgrade_id}</le>")

                                        await asyncio.sleep(delay=5)

                                        status, upgrades = await buy_upgrade(http_client=http_client,
                                                                             upgrade_id=upgrade_id)

                                        if status is True:
                                            earn_on_hour += profit
                                            balance -= price
                                            logger.success(f"{self.session_name} | "
                                                           f"Successfully upgraded <le>{upgrade_id}</le> with price <lr>{price:,}</lr> to <m>{level}</m> lvl | "
                                                           f"Earn every hour: <ly>{earn_on_hour:,}</ly> (<lg>+{profit:,}</lg>) | "
                                                           f"Money left: <le>{balance:,}</le>")

                                            await asyncio.sleep(delay=1)

                                    await asyncio.sleep(delay=2)

                                    status = await claim_daily_combo(http_client=http_client)
                                    if status is True:
                                        logger.success(f"{self.session_name} | Successfully claimed daily combo | "
                                                       f"Bonus: <lg>+{bonus:,}</lg>")

                    await asyncio.sleep(delay=randint(2, 4))

                    if settings.APPLY_DAILY_REWARD and datetime.now().hour >= settings.WAKE_UP:
                        tasks = await get_tasks(http_client=http_client)

                        daily_task = tasks[-1]
                        rewards = daily_task['rewardsByDays']
                        is_completed = daily_task['isCompleted']
                        days = daily_task['days']

                        await asyncio.sleep(delay=2)

                        if not is_completed:
                            task, profile_data = await check_task(http_client=http_client, task_id="streak_days")
                            is_completed = task.get('isCompleted')

                            if is_completed:
                                logger.success(f"{self.session_name} | Successfully get daily reward | "
                                               f"Days: <lm>{days}</lm> | Reward coins: <lg>+{rewards[days - 1]['rewardCoins']}</lg>")
                        else:
                            logger.info(f"{self.session_name} | Daily Reward already claimed today")

                        await get_tasks(http_client=http_client)
                        await get_upgrades(http_client=http_client)

                    await asyncio.sleep(delay=randint(2, 4))

                    daily_cipher = game_config.get('dailyCipher')
                    if daily_cipher and settings.APPLY_DAILY_CIPHER and datetime.now().hour >= settings.WAKE_UP:
                        cipher = daily_cipher['cipher']
                        bonus = daily_cipher['bonusCoins']
                        is_claimed = daily_cipher['isClaimed']

                        if not is_claimed and cipher:
                            decoded_cipher = decode_cipher(cipher=cipher)

                            status = await claim_daily_cipher(http_client=http_client, cipher=decoded_cipher)
                            if status is True:
                                logger.success(f"{self.session_name} | "
                                               f"Successfully claim daily cipher: <ly>{decoded_cipher}</ly> | "
                                               f"Bonus: <lg>+{bonus:,}</lg>")

                        await asyncio.sleep(delay=2)

                    await asyncio.sleep(delay=randint(2, 4))

                    daily_mini_game = game_config.get('dailyKeysMiniGames')
                    if daily_mini_game and settings.APPLY_DAILY_MINI_GAME and datetime.now().hour >= settings.WAKE_UP:
                        candles_mini_game = daily_mini_game.get('Candles')
                        if candles_mini_game:
                            is_claimed = candles_mini_game['isClaimed']
                            seconds_to_next_attempt = candles_mini_game['remainSecondsToNextAttempt']
                            start_date = candles_mini_game['startDate']
                            mini_game_id = candles_mini_game['id']

                            if not is_claimed and seconds_to_next_attempt <= 0:
                                game_sleep_time = randint(12, 26)

                                encoded_body = await get_mini_game_cipher(
                                    user_id=user_id,
                                    start_date=start_date,
                                    mini_game_id=mini_game_id,
                                    score=0
                                )

                                if encoded_body:
                                    await start_daily_mini_game(http_client=http_client,
                                                                mini_game_id=mini_game_id)

                                    logger.info(f"{self.session_name} | "
                                                f"Sleep <lw>{game_sleep_time}s</lw> in Mini Game <lm>{mini_game_id}</lm>")
                                    await asyncio.sleep(delay=game_sleep_time)

                                    profile_data, daily_mini_game, bonus = await claim_daily_mini_game(
                                        http_client=http_client, cipher=encoded_body, mini_game_id=mini_game_id)

                                    await asyncio.sleep(delay=2)

                                    if daily_mini_game:
                                        is_claimed = daily_mini_game['isClaimed']

                                        if is_claimed:
                                            new_total_keys = profile_data.get('totalKeys', total_keys)

                                            logger.success(f"{self.session_name} | "
                                                           f"Successfully claimed Mini Game <lm>{mini_game_id}</lm> | "
                                                           f"Total keys: <le>{new_total_keys}</le> (<lg>+{bonus}</lg>)")
                            else:
                                if is_claimed:
                                    logger.info(
                                        f"{self.session_name} | Daily Mini Game <lm>{mini_game_id}</lm> already claimed today")
                                elif seconds_to_next_attempt > 0:
                                    logger.info(f"{self.session_name} | "
                                                f"Need <lw>{seconds_to_next_attempt}s</lw> to next attempt in Mini Game <lm>{mini_game_id}</lm>")
                                elif not encoded_body:
                                    logger.info(
                                        f"{self.session_name} | Key for Mini Game <lm>{mini_game_id}</lm> is not found")

                        await asyncio.sleep(delay=randint(2, 4))

                        for _ in range(randint(a=settings.GAMES_COUNT[0], b=settings.GAMES_COUNT[1])):
                            game_config = await get_game_config(http_client=http_client)
                            daily_mini_game = game_config.get('dailyKeysMiniGames')
                            if daily_mini_game and settings.APPLY_DAILY_MINI_GAME:
                                tiles_mini_game = daily_mini_game.get('Tiles')
                                if tiles_mini_game:
                                    is_claimed = tiles_mini_game['isClaimed']
                                    seconds_to_next_attempt = tiles_mini_game['remainSecondsToNextAttempt']
                                    start_date = tiles_mini_game['startDate']
                                    mini_game_id = tiles_mini_game['id']
                                    remain_points = tiles_mini_game['remainPoints']
                                    max_points = tiles_mini_game['maxPoints']

                                if not is_claimed and remain_points > 0:
                                    game_sleep_time = randint(a=settings.SLEEP_MINI_GAME_TILES[0],
                                                              b=settings.SLEEP_MINI_GAME_TILES[1])
                                    game_score = randint(a=settings.SCORE_MINI_GAME_TILES[0],
                                                         b=settings.SCORE_MINI_GAME_TILES[1])

                                    if game_score > remain_points:
                                        game_score = remain_points

                                    logger.info(f"{self.session_name} | "
                                                f"Remain points <lg>{remain_points}/{max_points}</lg> in <lm>{mini_game_id}</lm> | "
                                                f"Sending score <lg>{game_score}</lg>")

                                    encoded_body = await get_mini_game_cipher(
                                        user_id=user_id,
                                        start_date=start_date,
                                        mini_game_id=mini_game_id,
                                        score=game_score
                                    )

                                    if encoded_body:
                                        await start_daily_mini_game(http_client=http_client, mini_game_id=mini_game_id)

                                        logger.info(f"{self.session_name} | "
                                                    f"Sleep <lw>{game_sleep_time}s</lw> in Mini Game <lm>{mini_game_id}</lm>")
                                        await asyncio.sleep(delay=game_sleep_time)

                                        profile_data, daily_mini_game, bonus = await claim_daily_mini_game(
                                            http_client=http_client, cipher=encoded_body, mini_game_id=mini_game_id)

                                        await asyncio.sleep(delay=2)

                                        if bonus:
                                            new_balance = int(profile_data.get('balanceCoins', 0))
                                            balance = new_balance

                                            logger.success(f"{self.session_name} | "
                                                           f"Successfully claimed Mini Game <lm>{mini_game_id}</lm> | "
                                                           f"Balance <le>{balance:,}</le> (<lg>+{bonus:,}</lg>)")
                                else:
                                    if is_claimed or remain_points == 0:
                                        logger.info(
                                            f"{self.session_name} | Daily Mini Game <lm>{mini_game_id}</lm> already claimed today")
                                        break
                                    elif seconds_to_next_attempt > 0:
                                        logger.info(f"{self.session_name} | "
                                                    f"Need <lw>{seconds_to_next_attempt}s</lw> to next attempt in Mini Game <lm>{mini_game_id}</lm>")
                                        break
                                    elif not encoded_body:
                                        logger.info(
                                            f"{self.session_name} | Key for Mini Game <lm>{mini_game_id}</lm> is not found")
                                        break

                        await asyncio.sleep(delay=randint(2, 4))

                    if settings.AUTO_COMPLETE_TASKS and datetime.now().hour >= settings.WAKE_UP:
                        tasks = await get_tasks(http_client=http_client)
                        for task in tasks:
                            task_id = task['id']
                            reward = task['rewardCoins']
                            is_completed = task['isCompleted']

                            if not task_id.startswith('hamster_youtube'):
                                continue

                            if not is_completed and reward > 0:
                                logger.info(f"{self.session_name} | "
                                            f"Sleep <lw>3s</lw> before complete <ly>{task_id}</ly> task")
                                await asyncio.sleep(delay=3)

                                task, profile_data = await check_task(http_client=http_client, task_id=task_id)
                                is_completed = task.get('isCompleted')

                                if is_completed:
                                    balance = int(profile_data.get('balanceCoins', 0))
                                    logger.success(f"{self.session_name} | "
                                                   f"Successfully completed <ly>{task_id}</ly> task | "
                                                   f"Balance: <lc>{balance}</lc> (<lg>+{reward}</lg>)")

                                    tasks = await get_tasks(http_client=http_client)
                                else:
                                    logger.info(f"{self.session_name} | Task <ly>{task_id}</ly> is not complete")

                        await get_upgrades(http_client=http_client)

                    await asyncio.sleep(delay=randint(2, 4))

                    exchange_id = profile_data.get('exchangeId')
                    if not exchange_id:
                        status = await select_exchange(http_client=http_client, exchange_id='bybit')
                        if status is True:
                            logger.success(f"{self.session_name} | Successfully selected exchange <ly>Bybit</ly>")

                    await asyncio.sleep(delay=randint(2, 4))

                    # Купляємо скіни
                    if settings.AUTO_BUY_SKINS and datetime.now().hour >= settings.WAKE_UP:
                        try:
                            skins = (
                                await get_version_config(http_client=http_client, config_version=config_version)).get(
                                'config', {}).get('skins', [])

                            bought_skins_ids = {skin.get('skinId') for skin in
                                                profile_data.get('skin', {}).get('available', [])}

                            bought_skins = len(bought_skins_ids)

                            logger.info(f"{self.session_name} | Bought Skins: <lg>{bought_skins}</lg>")

                            available_skins = [
                                skin for skin in skins
                                if skin.get('price', 0) <= settings.MAX_PRICE_SKIN
                                   and skin.get('id') not in bought_skins_ids
                                   and not skin.get('expiresAt')
                            ]

                            if available_skins:
                                skin_to_buy = min(available_skins, key=lambda x: x['price'])
                                skin_to_buy_name = skin_to_buy['name']

                                if balance - settings.BALANCE_TO_SAVE >= skin_to_buy['price']:
                                    logger.info(
                                        f"{self.session_name} | Sleep <lw>5s</lw> before buying a new skin <le>{skin_to_buy_name}</le>")
                                    await asyncio.sleep(5)

                                    if await buy_skin(http_client=http_client, skin_id=skin_to_buy['id']):
                                        balance -= skin_to_buy['price']
                                        logger.success(
                                            f"{self.session_name} | Successfully bought a new skin: <le>{skin_to_buy_name}</le> | Price: <lr>{skin_to_buy['price']:,}</lr> | Money left: <le>{balance:,}</le>")

                                        logger.info(
                                            f"{self.session_name} | Sleep <lw>5s</lw> before selecting a new skin <le>{skin_to_buy_name}</le>")
                                        await asyncio.sleep(5)

                                        if await select_skin(http_client=http_client, skin_id=skin_to_buy['id']):
                                            logger.success(
                                                f"{self.session_name} | Successfully new skin is selected: <le>{skin_to_buy_name}</le>")
                        except Exception as e:
                            logger.error(f"{self.session_name} | Error in AUTO_BUY_SKINS: {str(e)}")

                    await asyncio.sleep(delay=randint(6, 14))

                    # Качаємо картки
                    if settings.AUTO_UPGRADE and datetime.now().hour >= settings.WAKE_UP:
                        for _ in range(settings.UPGRADES_COUNT):
                            available_upgrades = [
                                data for data in upgrades
                                if data['isAvailable'] is True
                                   and data['isExpired'] is False
                                   and data.get('cooldownSeconds', 0) <= 1801
                                   and data.get('maxLevel', data['level']) >= data['level']
                            ]

                            queue = []

                            for upgrade in available_upgrades:
                                upgrade_id = upgrade['id']
                                level = upgrade['level']
                                price = upgrade['price']
                                profit = upgrade['profitPerHourDelta']

                                significance = profit / max(price, 1)

                                free_money = balance - settings.BALANCE_TO_SAVE

                                if ((free_money * 0.7) >= price
                                        and profit > 0
                                        and level <= settings.MAX_LEVEL
                                        and price <= settings.MAX_PRICE
                                        and significance >= settings.BUY_RATIO):
                                    heapq.heappush(queue, (-significance, upgrade_id, upgrade))

                            if not queue:
                                continue

                            top_card = heapq.nsmallest(1, queue)[0]
                            upgrade = top_card[2]
                            upgrade_id = upgrade['id']
                            level = upgrade['level']
                            price = upgrade['price']
                            profit = upgrade['profitPerHourDelta']
                            coin_name = upgrade['name']
                            cooldown_seconds = upgrade.get('cooldownSeconds', 0)

                            if not cooldown_seconds:
                                logger.info(
                                    f'{self.session_name} | Sleep 5s before upgrade <e>{coin_name}</e>'
                                )
                                await asyncio.sleep(delay=5)

                            elif cooldown_seconds < 1801:
                                logger.info(
                                    f'{self.session_name} | Sleep {cooldown_seconds + 12:,}s before upgrade <e>{coin_name}</e>')

                                # await asyncio.sleep(delay=cooldown_seconds + 12)

                                countdown_timer(cooldown_seconds + 12)

                            else:
                                continue

                            status, upgrades = await buy_upgrade(http_client=http_client, upgrade_id=upgrade_id)

                            if status is True:
                                earn_on_hour += profit
                                balance -= price
                                logger.success(f"{self.session_name} | "
                                               f"Successfully upgraded <le>{upgrade_id}</le> with price <lr>{price:,}</lr> to <m>{level}</m> lvl | "
                                               f"Earn every hour: <ly>{earn_on_hour:,}</ly> (<lg>+{profit:,}</lg>) | "
                                               f"Money left: <le>{balance:,}</le>")

                                await asyncio.sleep(delay=1)

                                continue

                    await asyncio.sleep(delay=randint(6, 14))

                    # Підбираємо коди
                    if settings.APPLY_PROMO_CODES and datetime.now().hour >= settings.WAKE_UP:

                        promos_data = await get_promos(http_client=http_client)
                        promo_states = promos_data.get('states', [])

                        promo_activates = {promo['promoId']: promo['receiveKeysToday']
                                           for promo in promo_states}

                        found_keys = sum([promo['receiveKeysToday'] for promo in promo_states])

                        all_keys = len(promo_states) * 4

                        logger.info(
                            f"{self.session_name} | <lg>{found_keys}</lg> keys out of <lg>{all_keys}</lg> are activated!")

                        # if found_keys >= int((all_keys * settings.PER_ENTERED_KEYS) / 100):
                        #     continue

                        apps_info = [
                            {
                                "promoId": "c4480ac7-e178-4973-8061-9ed5b2e17954",
                                "appToken": "82647f43-3f87-402d-88dd-09a90025313f",
                                "minWaitAfterLogin": 20,
                                "name": "Bike Ride 3D"
                            },
                            {
                                "promoId": "fe693b26-b342-4159-8808-15e3ff7f8767",
                                "appToken": "74ee0b5b-775e-4bee-974f-63e7f4d5bacb",
                                "minWaitAfterLogin": 121,
                                "name": "CLONE"
                            },
                            {
                                "promoId": "b4170868-cef0-424f-8eb9-be0622e8e8e3",
                                "appToken": "d1690a07-3780-4068-810f-9b5bbf2931b2",
                                "minWaitAfterLogin": 21,
                                "name": "Chain Cube 2048"
                            },
                            {
                                "promoId": "43e35910-c168-4634-ad4f-52fd764a843f",
                                "appToken": "d28721be-fd2d-4b45-869e-9f253b554e50",
                                "minWaitAfterLogin": 21,
                                "name": "Train Miner"
                            },
                            {
                                "promoId": "dc128d28-c45b-411c-98ff-ac7726fbaea4",
                                "appToken": "8d1cc2ad-e097-4b86-90ef-7a27e19fb833",
                                "minWaitAfterLogin": 21,
                                "name": "Merge Away"
                            },
                            {
                                "promoId": "61308365-9d16-4040-8bb0-2f4a4c69074c",
                                "appToken": "61308365-9d16-4040-8bb0-2f4a4c69074c",
                                "minWaitAfterLogin": 21,
                                "name": "Twerk Race"
                            },
                            {
                                "promoId": "2aaf5aee-2cbc-47ec-8a3f-0962cc14bc71",
                                "appToken": "2aaf5aee-2cbc-47ec-8a3f-0962cc14bc71",
                                "minWaitAfterLogin": 31,
                                "name": "Polysphere"
                            },
                            {
                                "promoId": "8814a785-97fb-4177-9193-ca4180ff9da8",
                                "appToken": "8814a785-97fb-4177-9193-ca4180ff9da8",
                                "minWaitAfterLogin": 31,
                                "name": "RACE"
                            },
                            {
                                "promoId": "ef319a80-949a-492e-8ee0-424fb5fc20a6",
                                "appToken": "ef319a80-949a-492e-8ee0-424fb5fc20a6",
                                "minWaitAfterLogin": 31,
                                "name": "Mow and Trim"
                            },
                            {
                                "promoId": "bc0971b8-04df-4e72-8a3e-ec4dc663cd11",
                                "appToken": "bc0971b8-04df-4e72-8a3e-ec4dc663cd11",
                                "minWaitAfterLogin": 31,
                                "name": "CafeDash"
                            },
                            {
                                "promoId": "b2436c89-e0aa-4aed-8046-9b0515e1c46b",
                                "appToken": "b2436c89-e0aa-4aed-8046-9b0515e1c46b",
                                "minWaitAfterLogin": 31,
                                "name": "Zoopolis"
                            },
                            {
                                "promoId": "c7821fa7-6632-482c-9635-2bd5798585f9",
                                "appToken": "b6de60a0-e030-48bb-a551-548372493523",
                                "minWaitAfterLogin": 61,
                                "name": "Gangs Wars"
                            }
                        ]

                        # apps_info = await get_apps_info(http_client=http_client)
                        apps = {
                            app['promoId']: {
                                'appToken': app['appToken'],
                                'event_timeout': app['minWaitAfterLogin']
                            } for app in apps_info
                        }

                        promos = promos_data.get('promos', [])

                        shuffle(promos)

                        for promo in promos:
                            promo_id = promo['promoId']

                            app = apps.get(promo_id)

                            if not app:
                                continue

                            app_token = app.get('appToken')
                            event_timeout = app.get('event_timeout')

                            if not app_token:
                                continue

                            title = promo['title']['en']
                            keys_per_day = promo['keysPerDay']
                            keys_per_code = 1

                            today_promo_activates_count = promo_activates.get(promo_id, 0)

                            if today_promo_activates_count >= keys_per_day:
                                logger.info(f"{self.session_name} | "
                                            f"Promo Codes already claimed today for <lm>{title}</lm> game")
                                continue

                            while today_promo_activates_count < keys_per_day:

                                promo_delay = randint(310, 470)

                                logger.info(
                                    f"{self.session_name} | Sleep <lc>{promo_delay:,}</lc>s before activate "
                                    f"new promo code")

                                countdown_timer(promo_delay)

                                promo_code = await get_promo_code(app_token=app_token,
                                                                  promo_id=promo_id,
                                                                  promo_title=title,
                                                                  max_attempts=20,
                                                                  event_timeout=event_timeout,
                                                                  session_name=self.session_name,
                                                                  proxy=proxy)

                                if not promo_code:
                                    continue

                                profile_data, promo_state = await apply_promo(http_client=http_client,
                                                                              promo_code=promo_code)

                                if profile_data and promo_state:
                                    total_keys = profile_data.get('totalKeys', total_keys)
                                    today_promo_activates_count = promo_state.get('receiveKeysToday',
                                                                                  today_promo_activates_count)

                                    logger.success(f"{self.session_name} | "
                                                   f"Successfully activated promo code <lc>{promo_code}</lc> in <lm>{title}</lm> game | "
                                                   f"Get <ly>{today_promo_activates_count}</ly><lw>/</lw><ly>{keys_per_day}</ly> keys | "
                                                   f"Total keys: <le>{total_keys}</le> (<lg>+{keys_per_code}</lg>)")
                                else:
                                    logger.info(f"{self.session_name} | "
                                                f"Promo code <lc>{promo_code}</lc> was wrong in <lm>{title}</lm> game | "
                                                f"Trying again...")

                                await asyncio.sleep(delay=2)

                            break

                    await asyncio.sleep(delay=randint(6, 14))

                # Качаємо картки
                if settings.AUTO_UPGRADE and datetime.now().hour >= settings.WAKE_UP:
                    for _ in range(settings.UPGRADES_COUNT):
                        available_upgrades = [
                            data for data in upgrades
                            if data['isAvailable'] is True
                               and data['isExpired'] is False
                               and data.get('cooldownSeconds', 0) <= 1801
                               and data.get('maxLevel', data['level']) >= data['level']
                        ]

                        queue = []

                        for upgrade in available_upgrades:
                            upgrade_id = upgrade['id']
                            level = upgrade['level']
                            price = upgrade['price']
                            profit = upgrade['profitPerHourDelta']

                            significance = profit / max(price, 1)

                            free_money = balance - settings.BALANCE_TO_SAVE

                            if ((free_money * 0.7) >= price
                                    and profit > 0
                                    and level <= settings.MAX_LEVEL
                                    and price <= settings.MAX_PRICE
                                    and significance >= settings.BUY_RATIO):
                                heapq.heappush(queue, (-significance, upgrade_id, upgrade))

                        if not queue:
                            continue

                        top_card = heapq.nsmallest(1, queue)[0]
                        upgrade = top_card[2]
                        upgrade_id = upgrade['id']
                        level = upgrade['level']
                        price = upgrade['price']
                        profit = upgrade['profitPerHourDelta']
                        coin_name = upgrade['name']
                        cooldown_seconds = upgrade.get('cooldownSeconds', 0)

                        if not cooldown_seconds:
                            logger.info(
                                f'{self.session_name} | Sleep 5s before upgrade <e>{coin_name}</e>'
                            )
                            await asyncio.sleep(delay=5)

                        elif cooldown_seconds < 1801:
                            logger.info(
                                f'{self.session_name} | Sleep {cooldown_seconds + 12:,}s before upgrade <e>{coin_name}</e>')

                            # await asyncio.sleep(delay=cooldown_seconds + 12)

                            countdown_timer(cooldown_seconds + 12)

                        else:
                            continue

                        status, upgrades = await buy_upgrade(http_client=http_client, upgrade_id=upgrade_id)

                        if status is True:
                            earn_on_hour += profit
                            balance -= price
                            logger.success(f"{self.session_name} | "
                                           f"Successfully upgraded <le>{upgrade_id}</le> with price <lr>{price:,}</lr> to <m>{level}</m> lvl | "
                                           f"Earn every hour: <ly>{earn_on_hour:,}</ly> (<lg>+{profit:,}</lg>) | "
                                           f"Money left: <le>{balance:,}</le>")

                            await asyncio.sleep(delay=1)

                            continue

                await asyncio.sleep(delay=randint(6, 14))

                # ТАПАЄМО
                if settings.USE_TAPS and datetime.now().hour >= settings.WAKE_UP:
                    taps = randint(a=settings.RANDOM_TAPS_COUNT[0], b=settings.RANDOM_TAPS_COUNT[1])

                    profile_data = await send_taps(
                        http_client=http_client,
                        available_energy=available_energy,
                        taps=taps,
                    )

                    if not profile_data:
                        continue

                    available_energy = profile_data.get('availableTaps', 0)
                    new_balance = int(profile_data.get('balanceCoins', 0))
                    calc_taps = new_balance - balance
                    balance = new_balance
                    total = int(profile_data.get('totalCoins', 0))
                    earn_on_hour = profile_data['earnPassivePerHour']

                    logger.success(f"{self.session_name} | Successful tapped! | "
                                   f"Balance: <lc>{balance:,}</lc> (<lg>+{calc_taps:,}</lg>) | Energy: <le>{available_energy:,}</le>")

                await asyncio.sleep(delay=randint(6, 14))

                if available_energy < settings.MIN_AVAILABLE_ENERGY or not settings.USE_TAPS or not datetime.now().hour >= settings.WAKE_UP:
                    if settings.USE_TAPS and datetime.now().hour > 8:
                        boosts = await get_boosts(http_client=http_client)
                        energy_boost = next((boost for boost in boosts if boost['id'] == 'BoostFullAvailableTaps'), {})

                        if (settings.APPLY_DAILY_ENERGY is True
                                and energy_boost.get('cooldownSeconds', 0) == 0
                                and energy_boost.get('level', 0) <= energy_boost.get('maxLevel', 0)):
                            logger.info(f"{self.session_name} | Sleep <lw>5s</lw> before apply energy boost")
                            await asyncio.sleep(delay=5)

                            status = await apply_boost(http_client=http_client, boost_id='BoostFullAvailableTaps')
                            if status is True:
                                logger.success(f"{self.session_name} | Successfully apply energy boost")

                                await asyncio.sleep(delay=1)

                                continue

                    await http_client.close()
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    logger.info("<lr>***************************</lr>")
                    logger.info("<lr>Закрив сесію. Пішов спати )</lr>")
                    logger.info(f"<lr>**************************</lr>")

                    if datetime.now().hour >= settings.WAKE_UP:
                        random_sleep = randint(2500, 3610)
                    else:
                        random_sleep = randint(settings.SLEEP_BY_MIN_ENERGY[0], settings.SLEEP_BY_MIN_ENERGY[1])

                    if settings.USE_TAPS and datetime.now().hour >= settings.WAKE_UP:
                        logger.info(f"{self.session_name} | Minimum energy reached: <ly>{available_energy:.0f}</ly>")
                    logger.info(f"{self.session_name} | Sleep <lw>{random_sleep:,}s</lw>")

                    # await asyncio.sleep(delay=random_sleep)
                    countdown_timer(random_sleep)

                    access_token_created_time = 0

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=3)

            if settings.USE_TAPS and datetime.now().hour >= settings.WAKE_UP:
                sleep_between_clicks = randint(a=settings.SLEEP_BETWEEN_TAP[0], b=settings.SLEEP_BETWEEN_TAP[1])

                logger.info(f"Sleep <lw>{sleep_between_clicks}s</lw>")
                await asyncio.sleep(delay=sleep_between_clicks)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
