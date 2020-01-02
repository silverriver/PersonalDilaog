import requests
import time
import random
import sys
from multiprocessing import Process, Manager, current_process
sys.path.append('..')           # For unit test
from logger import crawler
from config import headers, conf
from login import get_cookies
from page_parse.basic import is_404
from db.redis_db import Cookies

DAXIANG_URL = 'http://tvp.daxiangdaili.com/ip/?tid={}&num={}&delay=2&category=2&longlife=5'
MOGU_URL = 'http://piping.mogumiao.com/proxy/api/get_ip_bs?appKey={key}&count={num}&expiryDate=5&format=2'
TEST_URL = 'http://help.weibo.com/ask'      # Weibo Help page
BASE_URL = 'http://weibo.com/p/{}{}/info?mod=pedit_more'
COOKIES = get_cookies()


class Proxy():
    def __init__(self):
        self.manager = Manager()
        self.PROXY_IP = self.manager.dict()
        self.Cache = self.manager.Queue()
        self.Flag = self.manager.Value('i', 0)

        ip_list = self.request_ip(10)
        for i in ip_list:
            self.Cache.put(i)

    def make_proxy_head(self, proc_name):
        if proc_name in self.PROXY_IP:
            return self.make_proxy_head_with_ip(self.PROXY_IP[proc_name])

    @classmethod
    def is_ip_port(cls, ip):
        ip = ip.strip()
        return ip and ip.count('.') is 3 and ip.count(':') is 1

    # Valid ip list will be returned if non_stop==True otherwise this function will stop after one request
    @classmethod
    def request_ip(cls, num, non_stop=True):
        url = MOGU_URL.format(key=conf.moguproxy_order(), num=num)
        try:
            resp = requests.get(url)
        except:
            if non_stop:
                crawler.error('Can not get proxy ip, Please check the account')
                time.sleep(cls.get_proxy_sleep_time())
                return cls.request_ip(num)
            else:
                return []

        if resp.status_code is not 200:
            if non_stop:
                crawler.error('Can not get proxy ip, Please check the account')
                time.sleep(cls.get_proxy_sleep_time())
                return cls.request_ip(num)
            else:
                return []
        cand_ip = resp.content.decode().split()
        cand_ip = [i for i in cand_ip if cls.is_ip_port(i)]
        if len(cand_ip) is 0:
            if non_stop:
                sleep_time = cls.get_proxy_sleep_time()
                crawler.warning('Proxy is empty, try after {}, Return from server: {}'.format(sleep_time,
                                                                                              resp.content.decode()))
                time.sleep(sleep_time)
                return cls.request_ip(num)
            else:
                return []
        return cand_ip

    @classmethod
    def make_proxy_head_with_ip(cls, ip):
        return {'http': 'http://' + ip}

    @classmethod
    def get_proxy_sleep_time(cls):
        return random.randint(conf.get_proxy_ip_min_req_interal(), conf.get_proxy_ip_max_req_interal())

    @classmethod
    def check_weibo_help_page(cls, resp):
        return resp.status_code == 200 and '微博帮助' in resp.content.decode()

    @classmethod
    def check_ip(cls, ip):
        if '.' not in ip:
            crawler.info('Ignore non ip {}'.format(ip))
            return False
        crawler.info('Checking {}'.format(ip))
        count = 0
        while count < conf.get_proxy_max_retries():
            crawler.info('Check count {}'.format(count))
            try:
                resp = requests.get(TEST_URL, headers=headers,
                                    timeout=conf.get_proxy_speed_filter(),
                                    proxies=cls.make_proxy_head_with_ip(ip),
                                    verify=False)
                if cls.check_weibo_help_page(resp):
                    crawler.info('{} is available'.format(ip))
                    return True

            except Exception as excep:
                crawler.debug('Exceptions are raised when filtering {}.Here are details:{}'.format(ip, excep))
            count += 1
            time.sleep(0.2)

        crawler.info('Http proxy: ' + ip + ' is filtered out')
        return False

    def pick_ip_from_list(self, ip_list):
        res = ''
        for ip in ip_list:
            if res is '' and self.check_ip(ip):
                res = ip
            else:
                self.Cache.put(ip)
        return res

    def pick_ip_from_cache(self):
        try:
            if self.Cache.empty():
                return ''
            ip = self.Cache.get()
            if ip and self.check_ip(ip):
                return ip
            else:
                return ''
        except Exception as exc:
            crawler.info('Fail to get from Cache, message returned is {}'.format(exc))
            return ''

    def is_proc_set(self, proc_name):
        return proc_name in self.PROXY_IP and self.PROXY_IP[proc_name] is not ''

    def get_ip(self, proc_name):
        if proc_name in self.PROXY_IP:
            return self.PROXY_IP[proc_name]
        else:
            return ''

    def set_ip_for_proc(self, proc_name, ip):
        self.PROXY_IP[proc_name] = ip

    def update_ip(self, proc_name):
        ip = self.pick_ip_from_cache()
        if ip is '':
            if self.Flag is 1:
                time.sleep(self.get_proxy_sleep_time())
                self.update_ip(proc_name)
                return

            self.Flag = 1       # manual lock to slow down the request
            cand_ip = self.request_ip(conf.get_proxy_ip_per_request(), non_stop=False)
            time.sleep(2)       # slow down the request
            self.Flag = 0

            if len(cand_ip) is 0:
                time.sleep(self.get_proxy_sleep_time())
                self.update_ip(proc_name)
                return
            ip = self.pick_ip_from_list(cand_ip)
            if ip is '':
                self.update_ip(proc_name)
                return
            crawler.info('find one from list {}'.format(ip))
        else:
            crawler.info('find one from queue {}'.format(ip))
        self.set_ip_for_proc(proc_name, ip)


if __name__ == '__main__':
    #test = requests.get(TEST_URL, proxies=Proxy.make_proxy_head_with_ip('123.160.34.35:41854'), headers=headers)
    #print (test.status_code)
    #sys.exit(0)
    proxy = Proxy()
    m = Manager()
    IP = m.list()
    print(TEST_URL)
    ip_count = 2
    print('ip_count', ip_count)

    def foo():
        global proxy
        proxy.update_ip(current_process().name)
        global IP
        IP.append(proxy.get_ip(current_process().name))
        print('IP: {}'.format(IP))
    for i in range(ip_count):
        print(i)
        p = Process(target=foo)
        p.start()
        p.join()

    try:
        for i in IP:
            print('get_proxies: ', Proxy.make_proxy_head_with_ip(i))
            url = BASE_URL.format('100505', '1197219380')
            #html = get_page(url, auth_level=1, need_proxy=True)
            resp = requests.get(url, headers=headers, cookies=COOKIES, proxies=Proxy.make_proxy_head_with_ip(i),
                                verify=False)

            if resp.text:
                page = resp.text.encode('utf-8', 'ignore').decode('utf-8')

            if not resp.text or resp.status_code == 414:
                print('Invalid IP: ', i)
            elif is_404(page):
                print('IP 404: ', i)

            #resq = requests.get(TEST_URL, proxies=Proxy.make_proxy_head_with_ip(i), headers=headers)
            print(resp.status_code)
    except Exception as e:
        print(e)
        pass
