import heapq
import asyncio
from time import time
from random import randint
from datetime import datetime, timedelta

import aiohttp
import aiohttp_proxy
from pyrogram import Client

from bot.config import settings
from bot.utils.logger import logger
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
    send_taps)
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
            return

        while True:
            try:
                if http_client.closed:
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    proxy_conn = aiohttp_proxy.ProxyConnector().from_url(proxy) if proxy else None
                    http_client = aiohttp.ClientSession(headers=headers, connector=proxy_conn)

                if time() - access_token_created_time >= 3600:
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

                    logger.info(f"{self.session_name} | Last passive earn: <lg>+{last_passive_earn:,}</lg> | "
                                f"Earn every hour: <ly>{earn_on_hour:,}</ly> | Total keys: <le>{total_keys}</le>")

                    available_energy = profile_data.get('availableTaps', 0)
                    balance = int(profile_data.get('balanceCoins', 0))

                    upgrades = upgrades_data['upgradesForBuy']
                    daily_combo = upgrades_data.get('dailyCombo')

                    if settings.AUTO_COMPLETE_TASKS:
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

                if settings.USE_TAPS:
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

                # AUTO UPGRADE

                if available_energy < settings.MIN_AVAILABLE_ENERGY or not settings.USE_TAPS:
                    if settings.USE_TAPS:
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

                    random_sleep = randint(settings.SLEEP_BY_MIN_ENERGY[0], settings.SLEEP_BY_MIN_ENERGY[1])

                    if settings.USE_TAPS:
                        logger.info(f"{self.session_name} | Minimum energy reached: <ly>{available_energy:.0f}</ly>")
                    logger.info(f"{self.session_name} | Sleep <lw>{random_sleep:,}s</lw>")

                    await asyncio.sleep(delay=random_sleep)

                    access_token_created_time = 0

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=3)

            if settings.USE_TAPS:
                sleep_between_clicks = randint(a=settings.SLEEP_BETWEEN_TAP[0], b=settings.SLEEP_BETWEEN_TAP[1])

                logger.info(f"Sleep <lw>{sleep_between_clicks}s</lw>")
                await asyncio.sleep(delay=sleep_between_clicks)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
