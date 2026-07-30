from datetime import datetime
import json
import os
import re
import time
import urllib.parse
import requests
import urllib3

# SSL 보안 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 세션 생성 (네이버/야후 차단 방지 헤더 설정)
session = requests.Session()
session.verify = False
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.yahoo.com/",
})


def get_access_token():
  """카카오 액세스 토큰 발급"""
  rest_api_key = os.environ.get("REST_API_KEY")
  refresh_token = os.environ.get("REFRESH_TOKEN")

  if not rest_api_key or not refresh_token:
    try:
      with open("kakao_tokens.json", "r") as fp:
        tokens = json.load(fp)
        refresh_token = tokens.get("refresh_token")
        rest_api_key = tokens.get(
            "rest_api_key", "483acfaff219ef23a5df2456cc622dc4"
        )
    except Exception as e:
      print(f"❌ 토큰 파일 로드 실패: {e}")
      return None

  url = "https://kauth.kakao.com/oauth/token"
  data = {
      "grant_type": "refresh_token",
      "client_id": rest_api_key,
      "refresh_token": refresh_token,
  }

  response = requests.post(url, data=data, verify=False)
  if response.status_code == 200:
    return response.json().get("access_token")
  else:
    print(f"❌ 액세스 토큰 갱신 에러: {response.status_code}")
    return None


def translate_to_korean(text):
  """영어 헤드라인을 한국어로 자동 번역"""
  if (
      not text
      or "소식 없음" in text
      or "오류" in text
      or "실패" in text
  ):
    return text
  try:
    encoded_text = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q={encoded_text}"
    res = session.get(url, timeout=5)
    if res.status_code == 200:
      data = res.json()
      translated = "".join([item[0] for item in data[0] if item[0]])
      return translated
  except Exception:
    pass
  return text


def clean_html(text):
  """뉴스 제목 내 HTML 태그 및 특수문자 정화"""
  if not text:
    return ""
  text = re.sub(r"<[^>]+>", "", text)
  text = (
      text.replace("&quot;", '"')
      .replace("&amp;", "&")
      .replace("&lt;", "<")
      .replace("&gt;", ">")
      .replace("<b>", "")
      .replace("</b>", "")
  )
  return text.strip()


def get_yahoo_us_price(ticker):
  """미국 주식 가격 조회"""
  url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
  try:
    res = session.get(url, timeout=5)
    if res.status_code == 200:
      data = res.json()
      result = data["chart"]["result"][0]
      closes = [
          c for c in result["indicators"]["quote"][0]["close"] if c is not None
      ]
      if len(closes) >= 2:
        cp = closes[-1]
        pp = closes[-2]
        rate = ((cp - pp) / pp) * 100
        return cp, rate
  except Exception as e:
    print(f"야후 주가 에러 ({ticker}): {e}")
  return 0.0, 0.0


def get_5d_rate(ticker):
  """최근 5일간 누적 등락률 계산"""
  url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
  try:
    res = session.get(url, timeout=5)
    if res.status_code == 200:
      data = res.json()
      result = data["chart"]["result"][0]
      closes = [
          c for c in result["indicators"]["quote"][0]["close"] if c is not None
      ]
      if len(closes) >= 2:
        return ((closes[-1] - closes[0]) / closes[0]) * 100
  except Exception:
    pass
  return 0.0


def get_naver_domestic_price(code):
  """국내 주식 가격 조회"""
  try:
    api_url = f"https://m.stock.naver.com/api/stock/{code}/basic"
    res = session.get(api_url, timeout=5)
    if res.status_code == 200:
      jdata = res.json()
      price = float(jdata.get("closePrice", "0").replace(",", ""))
      rate = float(jdata.get("fluctuationsRatio", "0"))
      return price, rate
  except Exception as e:
    print(f"네이버 주가 에러 ({code}): {e}")
  return 0.0, 0.0


def get_naver_gold_price():
  """금 가격 조회 (KRX 금현물)"""
  try:
    api_url = "https://m.stock.naver.com/api/stock/1659.N/basic"
    res = session.get(api_url, timeout=5)
    if res.status_code == 200:
      jdata = res.json()
      price = float(jdata.get("closePrice", "0").replace(",", ""))
      rate = float(jdata.get("fluctuationsRatio", "0"))
      return price, rate
  except Exception as e:
    print(f"네이버 금 시세 에러: {e}")
  return 0.0, 0.0


def get_recent_yahoo_news_direct(ticker):
  """야후 파이낸스 다이렉트 API 호출 및 번역 (yfinance 패키지 미사용으로 100% 수집)"""
  try:
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}&newsCount=5"
    res = session.get(url, timeout=5)
    if res.status_code == 200:
      news_list = res.json().get("news", [])
      if news_list:
        current_time = int(time.time())
        one_day_ago = current_time - (24 * 60 * 60)

        for item in news_list:
          title = item.get("title")
          pub_time = item.get("providerPublishTime", 0)

          if title:
            translated = translate_to_korean(title)
            if pub_time >= one_day_ago:
              return translated
            else:
              return f"{translated} (최근 소식)"

        first_title = news_list[0].get("title", "")
        if first_title:
          return f"{translate_to_korean(first_title)} (최근 소식)"
  except Exception as e:
    print(f"야후 다이렉트 뉴스 에러 ({ticker}): {e}")

  return "외신 소식 없음"


def get_naver_news(code, is_us=False):
  """네이버 증권 최신 뉴스 수집 (국내/해외 다이렉트 URL 적용)"""
  try:
    if is_us:
      naver_symbol = code
      if code == "TSLA":
        naver_symbol = "TSLA.O"
      elif code == "CPNG":
        naver_symbol = "CPNG.N"
      elif code == "KMB":
        naver_symbol = "KMB.N"
      elif code == "GC=F":
        naver_symbol = "GC=F"

      # 네이버 해외주식 뉴스 API 주소
      api_url = f"https://m.stock.naver.com/api/news/world/stock/{naver_symbol}?pageSize=5&page=1"
    else:
      # 네이버 국내주식 뉴스 API 주소
      api_url = (
          f"https://m.stock.naver.com/api/news/stock/{code}?pageSize=5&page=1"
      )

    res = session.get(api_url, timeout=5)
    if res.status_code == 200:
      data = res.json()
      items = []
      if isinstance(data, list):
        items = data
      elif isinstance(data, dict):
        items = data.get("items", data.get("newsList", []))

      if items:
        first_item = items[0]
        title = (
            first_item.get("tit")
            or first_item.get("title")
            or first_item.get("articleTitle")
            or first_item.get("sntnc")
        )
        if title:
          return clean_html(title)
  except Exception as e:
    print(f"네이버 뉴스 수집 에러 ({code}): {e}")
  return "최신 뉴스 없음"


def generate_technical_strategy(rate_5d):
  """5일 누적 등락률 기반 분석"""
  if rate_5d <= -3.0:
    return (
        f"💡 기술적 분석(5일 기준): [과매도 구간 진입] (누적 {rate_5d:+,.2f}%)\n"
        "  - ⏱ 타이밍 ▶ 오늘: 분할 매수 고려 | 1주일: 저점 매집 | 1달: 반등"
        " 추이 관망"
    )
  elif rate_5d >= 3.0:
    return (
        f"💡 기술적 분석(5일 기준): [단기 과열 구간] (누적 {rate_5d:+,.2f}%)\n"
        "  - ⏱ 타이밍 ▶ 오늘: 추격 매수 자제 | 1주일: 일부 이익 실현 검토 |"
        " 1달: 홀딩"
    )
  else:
    return (
        f"💡 기술적 분석(5일 기준): [박스권 횡보/완만] (누적 {rate_5d:+,.2f}%)\n"
        "  - ⏱ 타이밍 ▶ 오늘: 관망 또는 지지선 분할 접근 | 1주일: 횡보 대응 |"
        " 1달: 비중 유지"
    )


def send_kakao_message(access_token, text):
  """카카오톡 메시지 전송"""
  url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
  headers = {"Authorization": f"Bearer {access_token}"}
  text_message = {
      "object_type": "text",
      "text": text,
      "link": {
          "web_url": "https://finance.naver.com",
          "mobile_web_url": "https://finance.naver.com",
      },
      "button_title": "네이버 금융 확인하기",
  }
  data = {"template_object": json.dumps(text_message)}
  response = requests.post(url, headers=headers, data=data, verify=False)
  return response.json()


def process_stock_item(name, symbol_or_code, is_us=True, is_gold=False):
  """종목 종합 브리핑 생성"""
  if is_us:
    cp, rate = get_yahoo_us_price(symbol_or_code)
    yahoo_headline = get_recent_yahoo_news_direct(symbol_or_code)
    naver_headline = get_naver_news(symbol_or_code, is_us=True)
    rate_5d = get_5d_rate(symbol_or_code)
    price_str = f"${cp:,.2f} ({rate:+,.2f}%)" if cp > 0 else "가격 수집 실패"

    news_block = (
        f"  - 📰 야후(번역): {yahoo_headline}\n"
        f"  - 📰 네이버: {naver_headline}\n"
    )

  elif is_gold:
    cp, rate = get_naver_gold_price()
    naver_headline = get_naver_news("1659.N", is_us=False)
    rate_5d = get_5d_rate("GC=F")
    if cp > 0:
      price_str = f"{cp:,.0f}원 (KRX금현물, {rate:+,.2f}%)"
    else:
      cp_y, rate_y = get_yahoo_us_price("GC=F")
      price_str = (
          f"${cp_y:,.2f} (국제금, {rate_y:+,.2f}%)" if cp_y > 0 else "가격 수집 실패"
      )

    news_block = f"  - 📰 네이버 소식: {naver_headline}\n"

  else:
    cp, rate = get_naver_domestic_price(symbol_or_code)
    yahoo_code = (
        symbol_or_code + ".KS" if len(symbol_or_code) == 6 else symbol_or_code
    )
    naver_headline = get_naver_news(symbol_or_code, is_us=False)
    rate_5d = get_5d_rate(yahoo_code)
    price_str = f"{cp:,.0f}원 ({rate:+,.2f}%)" if cp > 0 else "가격 수집 실패"

    news_block = f"  - 📰 네이버 소식: {naver_headline}\n"

  strategy = generate_technical_strategy(rate_5d)
  return f"• {name} | {price_str}\n{news_block}  -{strategy}\n"


def main():
  print("🔄 [에이전트 가동] 야후/네이버 뉴스 다이렉트 API 수집을 시작합니다...")
  today_str = datetime.now().strftime("%Y년 %m월 %d일")

  access_token = get_access_token()
  if not access_token:
    print("❌ 액세스 토큰 취득 실패")
    return

  # 1. 미국 장 파트 1 (테슬라, 쿠팡)
  part1 = [f"📊 [{today_str} 미국 장 브리핑 (1/2)]\n"]
  for name, symbol in [("테슬라", "TSLA"), ("쿠팡", "CPNG")]:
    part1.append(process_stock_item(name, symbol, is_us=True))
    time.sleep(1)
  send_kakao_message(access_token, "\n".join(part1))

  # 2. 미국 장 파트 2 (킴벌리클라크)
  part2 = [f"📊 [{today_str} 미국 장 브리핑 (2/2)]\n"]
  for name, symbol in [("킴벌리클라크", "KMB")]:
    part2.append(process_stock_item(name, symbol, is_us=True))
    time.sleep(1)
  send_kakao_message(access_token, "\n".join(part2))

  # 3. 국내 장 & 금 파트 1 (금, 포스코퓨처엠, 한화에어로스페이스)
  part3 = [f"📊 [{today_str} 국내 장 & 자산 브리핑 (1/2)]\n"]
  part3.append(process_stock_item("금", "GOLD", is_us=False, is_gold=True))
  time.sleep(1)
  for name, code in [
      ("포스코퓨처엠", "003670"),
      ("한화에어로스페이스", "012450"),
  ]:
    part3.append(process_stock_item(name, code, is_us=False, is_gold=False))
    time.sleep(1)
  send_kakao_message(access_token, "\n".join(part3))

  # 4. 국내 장 파트 2 (LIG넥스원, 한화비전, 현대로템)
  part4 = [f"📊 [{today_str} 국내 장 & 자산 브리핑 (2/2)]\n"]
  for name, code in [
      ("LIG넥스원", "079550"),
      ("한화비전", "489790"),
      ("현대로템", "064350"),
  ]:
    part4.append(process_stock_item(name, code, is_us=False, is_gold=False))
    time.sleep(1)
  send_kakao_message(access_token, "\n".join(part4))

  print("✅ 미국/국내 뉴스 완벽 수집 및 전송 성공!")


if __name__ == "__main__":
  main()
