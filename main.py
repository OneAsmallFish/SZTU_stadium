import requests
import logging
import random
import time
from datetime import datetime, timedelta

# 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler("log.txt", encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(console)

# 请求头配置
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Content-Type': 'application/json'
}
requests.packages.urllib3.disable_warnings()

# 登录函数
def login(max_retries=5):
    url = "https://gym.sztu.edu.cn/mapi/auth/login?username=202401103010&password=sztu%40217186"
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, verify=False)
            response.raise_for_status()
            return response.json().get("data").get("web-x-auth-token")
        except requests.RequestException as e:
            logger.warning(f"登录失败，尝试重连 (尝试 {attempt + 1}/{max_retries}): {e}")
            time.sleep(random.uniform(0.5, 1.5))  # 随机延时
    raise Exception("登录失败，超过最大重试次数")

# 获取请求头
def get_headers():
    return {
        "Content-Length": "96",
        "Xweb_Xhr": "1",
        "Web-X-Auth-Token": login(),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090c11)XWEB/11275",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Referer": "https://servicewechat.com/wx841f34453e694e39/5/page-frame.html",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }

# 获取球场信息
def get_info(max_retries=20):
    url = "https://gym.sztu.edu.cn/mapi/venue/site/session/list"
    '''
    "blockType"中：1表示拼场，2表示包场
    "siteDateType"中：1表示当日，2表示次日
    '''
    payload = {"venueId": 3, "blockType": 2, "siteDateType": 2, "sessionType": 0, "stock": None, "timeQuantumType": None}
    headers = get_headers()

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            response.raise_for_status()
            data = response.json().get("data", [])
            if not data:
                logger.warning(f"获取到的球场信息为空，重试中 (尝试 {attempt + 1}/{max_retries})")
                time.sleep(random.uniform(0.5, 1.5))  # 随机延时
                continue
            return data
        except requests.RequestException as e:
            logger.warning(f"获取失败，尝试重连 (尝试 {attempt + 1}/{max_retries}): {e}")
            time.sleep(random.uniform(0.5, 1.5))  # 随机延时
    raise Exception("获取失败，超过最大重试次数")

# 处理球场信息
def found_info(data, target_start_time, date):
    last_record_id = None
    for record in data.get(date, []):
        if record["startTime"] == target_start_time:
            return record["id"]
        last_record_id = record["id"]  # 记录最后一个时间段的id
    return last_record_id  # 如果找不到target_start_time，返回最后一个时间段的id

# 预定球场
def place_booking(Id):
    url = "https://gym.sztu.edu.cn/mapi/user/order/create"
    payload = {"siteSessionId": Id, "pointsDeduction": 70, "payType": 5, "peerUserNum": []}
    headers = get_headers()

    start_time = time.time()  # 初始化开始时间

    while True:
        if time.time() - start_time > 360:  # 6分钟等于360秒
            logger.error("预订超时，超过6分钟")
            raise Exception("预订失败，超过6分钟")
        try:
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            response.raise_for_status()
            json_response = response.json()
            msg = json_response.get("msg")
            if "系统繁忙,请稍后再试" in msg or "当前时间不可预定，未到可提前预约时间" in msg:
                logger.warning(f"{msg}，稍后重试")
                time.sleep(random.uniform(0.5, 1.5))  # 随机延时
                continue
            elif "成功" in msg:  # 假设"成功"在成功消息中
                order = json_response.get("data", {}).get("orderNo")
                logger.info(msg)
                return msg, order
            else:
                logger.info(msg)
                return msg, None
        except requests.RequestException as e:
            logger.warning(f"预约请求失败，重试中: {e}")
            time.sleep(random.uniform(0.5, 1.5))  # 随机延时

# 支付函数
def pay_order(order, max_retries=5):
    url = "https://gym.sztu.edu.cn/mapi/pay/pay"
    payload = {"orderNo": order, "payType": 5}
    headers = get_headers()

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            response.raise_for_status()
            msg = response.json().get("msg")
            logger.info(msg)
            return msg
        except requests.RequestException as e:
            logger.warning(f"支付失败，尝试重连 (尝试 {attempt + 1}/{max_retries}): {e}")
            time.sleep(random.uniform(0.5, 1.5))  # 随机延时
    raise Exception("支付失败，超过最大重试次数")

# 主函数
def main():
    target_start_time = "20:20:00"
    '''
    订当日用 datetime.now().strftime("%Y-%m-%d")
    订次日用 (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    '''
    next_day_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    data = get_info()
    Id = found_info(data, target_start_time, next_day_date)
    if Id:
        msg, order = place_booking(Id)
        if "票已售罄" not in msg:
            pay_order(order)
        else:
            logger.info("票已售罄，跳过支付")
    else:
        logger.error("未找到匹配的开始时间")

if __name__ == "__main__":
    main()
