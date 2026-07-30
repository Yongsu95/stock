from datetime import datetime
import json
import os
import time
import requests
import urllib3
import yfinance as yf

# SSL 보안 경고 및 검증 무시 설정
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 세션 생성 (브라우저 위장)
session = requests.Session()
session.verify = False
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})


def get_access_token():
  """환경 변수(깃허브 시크릿) 또는 로컬 파일에서 카카오 토큰을 읽어

  최신 액세스 토큰을 실시간 발급받습니다.
  """
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
    print(response.json())
    return None


def get_yahoo_us_price(ticker):
  """미국 주식 가격 조회 (야후 파이낸스 API 직접 활용 - 전일 대비 등락률)"""
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
    print(f"야후 미국 주가 수집 에러 ({ticker}): {e}")
  return 0.0, 0.0


def get_5d_rate(ticker):
  """기술적 분석용 최근 5일간 누적 등락률 계산"""
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
        c_start = closes[0]
        c_end = closes[-1]
        rate_5d = ((c_end - c_start) / c_start) * 100
        return rate_5d
  except Exception:
    pass
  return 0.0


def get_naver_domestic_price(code):
  """국내 주식 가격 조회 (네이버 증권)"""
  try:
    api_url = f"https://m.stock.naver.com/api/stock/{code}/basic"
    res = session.get(api_url, timeout=5)
    if res.status_code == 200:
      jdata = res.json()
      price = float(jdata.get("closePrice", "0").replace(",", ""))
      rate = float(jdata.get("fluctuationsRatio", "0"))
      return price, rate
  except Exception as e:
    print(f"네이버 국내 주가 수집 에러 ({code}): {e}")
  return 0.0, 0.0


def get_naver_gold_price():
  """금 가격 조회 (네이버 증권 KRX 금현물 시세)"""
  try:
    api_url = "https://m.stock.naver.com/api/stock/1659.N/basic"
    res = session.get(api_url, timeout=5)
    if res.status_code == 200:
      jdata = res.json()
      price = float(jdata.get("closePrice", "0").replace(",", ""))
      rate = float(jdata.get("fluctuationsRatio", "0"))
      return price, rate
  except Exception as e:
    print(f"네이버 금 시세 수집 에러: {e}")
  return 0.0, 0.0


def get_recent_yahoo_news(ticker_symbol):
  """야후 파이낸스에서 24시간 이내 발생한 최신 뉴스 필터링"""
  try:
    tk = yf.Ticker(ticker_symbol, session=session)
    news_list = tk.news
    current_time = int(time.time())
    one_day_ago = current_time - (24 * 60 * 60)

    for news in news_list:
      pub_time = news.get("providerPublishTime", 0)
      if pub_time >= one_day_ago:
        return news.get("title", "제목 없음")

    return "24시간 내 새로운 외신 소식 없음"
  except Exception:
    return "24시간 내 새로운 외신 소식 없음"


def get_naver_news(code, is_us=False):
  """네이버 증권 모바일 API를 통해 최신 뉴스 수집"""
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
      api_url = f"https://m.stock.naver.com/api/stock/world/news?symbol={naver_symbol}&pageSize=5&page=1"
    else:
      api_url = f"https://m.stock.naver.com/api/stock/{code}/news?pageSize=5&page=1"

    res = session.get(api_url, timeout=5)
    if res.status_code == 200:
      data = res.json()
      items = data if isinstance(data, list) else data.get("items", [])
      if items:
        first_item = items[0]
        return first_item.get(
            "title", first_item.get("sntnc", "네이버 뉴스 없음")
        )
  except Exception:
    pass
  return "네이버 뉴스 없음"


def generate_technical_strategy(rate_5d):
  """최근 5일간의 누적 등락률(rate_5d)을 기반으로 기술적 분석 및 전략 생성"""
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
  """카카오톡 나에게 보내기 API 전송 함수"""
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
  """종목 하나의 가격, 야후/네이버 뉴스 및 5일 기술적 분석 데이터를 수집하여 반환"""
  if is_us:
    cp, rate = get_yahoo_us_price(symbol_or_code)
    yahoo_headline = get_recent_yahoo_news(symbol_or_code)
    naver_headline = get_naver_news(symbol_or_code, is_us=True)
    rate_5d = get_5d_rate(symbol_or_code)
    if cp > 0:
      price_str = f"${cp:,.2f} ({rate:+,.2f}%)"
    else:
      price_str = "가격 정보 수집 실패"
  elif is_gold:
    cp, rate = get_naver_gold_price()
    yahoo_headline = get_recent_yahoo_news("GC=F")
    naver_headline = get_naver_news("1659.N", is_us=False)
    rate_5d = get_5d_rate("GC=F")
    if cp > 0:
      price_str = f"{cp:,.0f}원 (KRX금현물, {rate:+,.2f}%)"
    else:
      cp_y, rate_y = get_yahoo_us_price("GC=F")
      cp, rate = cp_y, rate_y
      rate_5d = get_5d_rate("GC=F")
      price_str = (
          f"${cp_y:,.2f} (국제금, {rate_y:+,.2f}%)"
          if cp_y > 0
          else "가격 정보 수집 실패"
      )
  else:
    cp, rate = get_naver_domestic_price(symbol_or_code)
    yahoo_code = (
        symbol_or_code + ".KS" if len(symbol_or_code) == 6 else symbol_or_code
    )
    yahoo_headline = get_recent_yahoo_news(yahoo_code)
    naver_headline = get_naver_news(symbol_or_code, is_us=False)
    rate_5d = get_5d_rate(yahoo_code)
    if cp > 0:
      price_str = f"{cp:,.0f}원 ({rate:+,.2f}%)"
    else:
      price_str = "가격 정보 수집 실패"

  strategy = generate_technical_strategy(rate_5d)
  return (
      f"• {name} | {price_str}\n"
      f"  - 📰 야후(24h): {yahoo_headline}\n"
      f"  - 📰 네이버: {naver_headline}\n"
      f"  -{strategy}\n"
  )


def main():
  print(
      "🔄 [에이전트 가동] 야후와 네이버 뉴스를 모두 수집하여 분할 전송합니다..."
  )
  today_str = datetime.now().strftime("%Y년 %m월 %d일")

  access_token = get_access_token()
  if not access_token:
    print("❌ 유효한 액세스 토큰을 가져오지 못해 전송을 중단합니다.")
    return

  # -------------------------------------------------------------
  # [메시지 1] 미국 장 파트 1 (테슬라, 쿠팡)
  # -------------------------------------------------------------
  part1_report = [f"📊 [{today_str} 미국 장 브리핑 (1/2)]\n"]
  for name, symbol in [("테슬라", "TSLA"), ("쿠팡", "CPNG")]:
    part1_report.append(process_stock_item(name, symbol, is_us=True))
    time.sleep(1)
  res1 = send_kakao_message(access_token, "\n".join(part1_report))
  print(f"📩 미국(1/2) 전송 결과: {res1}")
  time.sleep(1)

  # -------------------------------------------------------------
  # [메시지 2] 미국 장 파트 2 (킴벌리클라크)
  # -------------------------------------------------------------
  part2_report = [f"📊 [{today_str} 미국 장 브리핑 (2/2)]\n"]
  for name, symbol in [("킴벌리클라크", "KMB")]:
    part2_report.append(process_stock_item(name, symbol, is_us=True))
    time.sleep(1)
  res2 = send_kakao_message(access_token, "\n".join(part2_report))
  print(f"📩 미국(2/2) 전송 결과: {res2}")
  time.sleep(1)

  # -------------------------------------------------------------
  # [메시지 3] 국내 장 & 금 파트 1 (금, 포스코퓨처엠, 한화에어로스페이스)
  # -------------------------------------------------------------
  part3_report = [f"📊 [{today_str} 국내 장 & 자산 브리핑 (1/2)]\n"]
  part3_report.append(
      process_stock_item("금", "GOLD", is_us=False, is_gold=True)
  )
  time.sleep(1)
  for name, code in [
      ("포스코퓨처엠", "003670"),
      ("한화에어로스페이스", "012450"),
  ]:
    part3_report.append(
        process_stock_item(name, code, is_us=False, is_gold=False)
    )
    time.sleep(1)
  res3 = send_kakao_message(access_token, "\n".join(part3_report))
  print(f"📩 국내(1/2) 전송 결과: {res3}")
  time.sleep(1)

  # -------------------------------------------------------------
  # [메시지 4] 국내 장 파트 2 (LIG넥스원, 한화비전, 현대로템)
  # -------------------------------------------------------------
  part4_report = [f"📊 [{today_str} 국내 장 & 자산 브리핑 (2/2)]\n"]
  for name, code in [
      ("LIG넥스원", "079550"),
      ("한화비전", "489790"),
      ("현대로템", "064350"),
  ]:
    part4_report.append(
        process_stock_item(name, code, is_us=False, is_gold=False)
    )
    time.sleep(1)
  res4 = send_kakao_message(access_token, "\n".join(part4_report))
  print(f"📩 국내(2/2) 전송 결과: {res4}")

  if all(
      r.get("result_code") == 0 for r in [res1, res2, res3, res4]
  ):
    print("✅ [성공] 야후+네이버 뉴스 동시 수집 브리핑 메시지 4개 분할 전송 완료!")
  else:
    print("❌ [에러 발생] 일부 메시지 전송 실패 확인 필요")


if __name__ == "__main__":
  main()
