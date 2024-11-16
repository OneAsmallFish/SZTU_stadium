import requests
import re
import base64
import ddddocr
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

# 验证码获取
def get_captcha(max_retries=20):
    url = "https://gym.sztu.edu.cn/mapi/auth/captcha"
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, verify=False)
            response.raise_for_status()
            data = response.json().get('data', {})
            captcha_base64 = data.get('captcha')
            uuid = data.get('uuid')

            if not captcha_base64 or not uuid:
                raise ValueError("无法获取验证码数据或UUID")

            uuid_suffix = uuid.split(':')[-1]
            image_data = base64.b64decode(captcha_base64)
            return image_data, uuid_suffix

        except requests.RequestException as e:
            logger.warning(f"获取验证码失败，尝试重新获取 (尝试 {attempt + 1}/{max_retries}): {e}")
            time.sleep(random.uniform(0.5, 1))
    raise Exception("获取验证码失败，超过最大尝试次数")

# 验证码识别
def recognize_captcha(image_data):
    ocr = ddddocr.DdddOcr()
    ocr.set_ranges("0123456789+-x/=")
    result = ocr.classification(image_data, probability=True)

    captcha_result = "".join(result['charsets'][temp.index(max(temp))] for temp in result['probability'])

    digits = re.findall(r'\d', captcha_result)
    operators = re.findall(r'[+-/*]', captcha_result)

    if len(digits) != 2 or len(operators) != 1:
        raise ValueError("无法识别正确的验证码格式")

    num1, num2 = map(int, digits)
    operator = operators[0]
    expression = f"{num1}{operator}{num2}"
    return eval(expression)

def captcha_code(max_retries=20):
    image_data, uuid_suffix = get_captcha(max_retries)
    code_result = recognize_captcha(image_data)
    logger.info("验证码识别成功")
    return code_result, uuid_suffix

# 登录函数
def login(max_retries=20):
    for attempt in range(max_retries):
        try:
            code, uuid = captcha_code()
            """
            在下面把你的账号密码进行替换
            """
            url = f"https://gym.sztu.edu.cn/mapi/auth/login?username=账号&password=密码&code={code}&uuid=captcha%3A{uuid}"
            response = requests.get(url, headers=HEADERS, verify=False)
            response.raise_for_status()
            json_response = response.json()
            
            # 检查 msg 是否包含 "success"
            if json_response.get("msg") != "success":
                logger.warning(f"登录失败，返回信息：{json_response.get('msg')}")
                raise ValueError("登录失败，未成功")
            
            return json_response.get("data").get("web-x-auth-token")
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"登录失败，尝试重连 (尝试 {attempt + 1}/{max_retries}): {e}")
            time.sleep(random.uniform(0.5, 1.5))  # 随机延时
    raise Exception("登录失败，超过最大重试次数")

# 获取请求头
def get_headers(auth_token):
    return {
        "Content-Length": "96",
        "Xweb_Xhr": "1",
        "Web-X-Auth-Token": auth_token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090c11)XWEB/11275",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Referer": "https://servicewechat.com/wx841f34453e694e39/5/page-frame.html",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }

# 获取球场信息
def get_info(auth_token, max_retries=20):
    url = "https://gym.sztu.edu.cn/mapi/venue/site/session/list"
    '''
    "blockType"中：1表示拼场，2表示包场
    "siteDateType"中：1表示当日，2表示次日
    '''
    payload = {"venueId": 3, "blockType": 2, "siteDateType": 2, "sessionType": 0, "stock": None, "timeQuantumType": None}
    headers = get_headers(auth_token)

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
    last_record = None
    for record in data.get(date, []):
        if record["startTime"] == target_start_time:
            return {"id": record["id"], "ticketPrice": record["ticketPrice"]}
        last_record = record  # 记录最后一个时间段的记录
    if last_record:
        return {"id": last_record["id"], "ticketPrice": last_record["ticketPrice"]}
    return None  # 如果找不到任何记录，返回None

# 预定球场
def place_booking(info, auth_token):
    url = "https://gym.sztu.edu.cn/mapi/user/order/create"
    payload = {
        "siteSessionId": info["id"], 
        "pointsDeduction": info["ticketPrice"], 
        "payType": 5, 
        "peerUserNum": []
    }
    headers = get_headers(auth_token)

    start_time = time.time()  # 初始化开始时间

    while True:
        if time.time() - start_time > 360:  # 6分钟等于360秒
            logger.error("预订超时，超过6分钟")
            raise Exception("预订失败，超过6分钟")
        try:
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=3)
            response.raise_for_status()
            json_response = response.json()
            msg = json_response.get("msg")
            if any(err_msg in msg for err_msg in ["系统繁忙,请稍后再试", "当前时间不可预定，未到可提前预约时间", "系统错误，请联系管理员"]):
                logger.warning(f"{msg}，稍后重试")
                time.sleep(random.uniform(0.3, 0.7))  # 随机延时
                continue
            elif "success" in msg:  # 假设"成功"在消息中
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
def pay_order(order, auth_token, max_retries=50):
    url = "https://gym.sztu.edu.cn/mapi/pay/pay"
    payload = {"orderNo": order, "payType": 5}
    headers = get_headers(auth_token)

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            response.raise_for_status()
            msg = response.json().get("msg")
            logger.info(msg)
            return msg
        except requests.RequestException as e:
            logger.warning(f"支付失败，尝试重连 (尝试 {attempt + 1}/{max_retries}): {e}")
            time.sleep(random.uniform(5, 10))  # 随机延时
    raise Exception("支付失败，超过最大重试次数")

# 主函数
def main():
    target_start_time = "20:20:00"
    '''
    订当日用 datetime.now().strftime("%Y-%m-%d")
    订次日用 (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    '''
    next_day_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    auth_token = login()  # 获取并存储auth_token
    data = get_info(auth_token)
    info = found_info(data, target_start_time, next_day_date)
    if info:
        msg, order = place_booking(info, auth_token)
        if "票已售罄" not in msg:
            pay_order(order, auth_token)
        else:
            logger.info("票已售罄，跳过支付")
    else:
        logger.error("未找到匹配的开始时间")

if __name__ == "__main__":
    main()
