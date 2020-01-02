import os
import time
import signal

import requests

from multiprocessing import current_process
from utils.proxy import Proxy
from config import headers
from logger import crawler
from login import get_cookies
from db.dao import LoginInfoOper
from utils import send_email
from db.redis_db import (
    Urls, Cookies)
from page_parse import (
    is_403, is_404, is_complete)
from decorators import (
    timeout_decorator, timeout)
from config import (
    get_timeout, get_crawl_interal, get_excp_interal, get_max_retries, get_proxy_time_out)


TIME_OUT = get_timeout()
INTERAL = get_crawl_interal()
MAX_RETRIES = get_max_retries()
EXCP_INTERAL = get_excp_interal()
COOKIES = get_cookies()
PROXY = Proxy()


def is_banned(url):
    if 'unfreeze' in url or 'accessdeny' in url or 'userblock' in url or 'verifybmobile' in url:
        return True
    return False


@timeout(200)
@timeout_decorator
def get_page(url, auth_level=2, is_ajax=False, need_proxy=False):
    """
    :param url: url to crawl
    :param auth_level: 0 stands for need nothing,1 stands for no login but need cookies,2 stands for need login.
    :param is_ajax: whether the request is ajax
    :param need_proxy: whether the request need a http/https proxy
    :return: response text, when a exception is raised, return ''
    """
    proc_name = current_process().name

    if need_proxy and not PROXY.is_proc_set(proc_name):
        PROXY.update_ip(proc_name)

    crawler.info('the crawling url is {url} , {proxy}, Proxy_ip:{ip}'.format(url=url, proxy=str(need_proxy),
                                                                             ip=PROXY.get_ip(proc_name)))
    count = 0

    while count < MAX_RETRIES:
        if auth_level == 2:
            cookie_count = 0
            while cookie_count < MAX_RETRIES:
                name_cookies = Cookies.fetch_cookies()

                if name_cookies is None:
                    crawler.warning('No cookie available, will try again later')
                    cookie_count += 1
                    time.sleep(EXCP_INTERAL)
                else:
                    break

            if name_cookies is None:
                crawler.warning('No cookie in cookies pool. Maybe all accounts are banned, or all cookies are expired')
                send_email()
                os.kill(os.getppid(), signal.SIGTERM)
        try:
            if auth_level == 2:
                if need_proxy:
                    resp = requests.get(url, headers=headers, cookies=name_cookies[1],
                                        proxies=PROXY.make_proxy_head(proc_name),
                                        timeout=get_proxy_time_out(), verify=False)
                else:
                    resp = requests.get(url, headers=headers, cookies=name_cookies[1], timeout=TIME_OUT, verify=False)
            elif auth_level == 1:
                if need_proxy:
                    resp = requests.get(url, headers=headers, cookies=COOKIES,
                                        proxies=PROXY.make_proxy_head(proc_name), timeout=get_proxy_time_out(),
                                        verify=False)
                else:
                    resp = requests.get(url, headers=headers, cookies=COOKIES, timeout=TIME_OUT, verify=False)
            else:
                if need_proxy:
                    resp = requests.get(url, headers=headers, proxies=PROXY.make_proxy_head(proc_name),
                                        timeout=get_proxy_time_out(), verify=False)
                else:
                    resp = requests.get(url, headers=headers, timeout=TIME_OUT, verify=False)
        except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout) as e:
            # not sure which exception should be catch to trigger this logic, which changes the Proxy IP
            crawler.warning('Proxy Exception are raised when crawling {}. Here are details:{}'.format(url, e))
            PROXY.update_ip(proc_name)
            crawler.info('Change Proxy IP to {}'.format(PROXY.get_ip(proc_name)))
            count += 0.5
            continue
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError, AttributeError) as e:
            crawler.warning('Excepitons are raised when crawling {}.Here are details:{}'.format(url, e))
            count += 1
            time.sleep(60)
            continue

        if resp.status_code == 414:
            crawler.warning('This ip has been blocked by weibo system {}'.format(PROXY.get_ip(proc_name)))
            if not need_proxy:
                send_email()
                os.kill(os.getppid(), signal.SIGTERM)
            else:
                time.sleep(60)
                PROXY.update_ip(proc_name)
                crawler.info('Change Proxy IP to {}'.format(PROXY.get_ip(proc_name)))
        if resp.text:
            page = resp.text.encode('utf-8', 'ignore').decode('utf-8')
        else:
            count += 1
            continue
        if auth_level == 2:
            # slow down to aviod being banned
            time.sleep(INTERAL)
            if is_banned(resp.url) or is_403(page):
                crawler.warning('Account {} has been banned'.format(name_cookies[0]))
                LoginInfoOper.freeze_account(name_cookies[0], 0)
                Cookies.delete_cookies(name_cookies[0])
                count += 1
                continue

            if not is_ajax and not is_complete(page):
                count += 1
                continue

        if is_404(page):
            crawler.warning('{} seems to be 404'.format(url))
            return ''
        Urls.store_crawl_url(url, 1)
        return page

    Urls.store_crawl_url(url, 0)
    return ''
