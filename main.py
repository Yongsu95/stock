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

# 디버그 모드: 환경변수 DEBUG_NEWS=1 로 실행하면
# 네이버 뉴스 API의 실제 응답 구조(키 이름)를 콘솔에 출력합니다.
# 원인 파악 후에는 다시 0(또는 미설정)으로 두세요.
DEBUG_NEWS = os.environ.get("DEBUG_NEWS", "0") == "1"

# 세션 생성 (네이버/야후 차단 방지 헤더 설정)
session = requests.Session()
session.verify = False
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
})

# 야후 전용 헤더 / 네이버 전용 헤더를 분리 (기존엔 Referer가 야후로 고정되어
# 네이버 요청에도 그대로 붙어나갔음)
YAHOO_HEADERS = {"Referer": "https://finance.yahoo.com/"}
NAVER_HEADERS = {"Referer": "https://m.stock.naver.com/"}

# -------------------------------------------------------------
# [지침 1] 종목별 검증 키워드 매핑 테이블 (NER & Keyword Verification)
# -------------------------------------------------------------
STOCK_KEYWORDS = {
    # 미국 주식
    "TSLA": ["테슬라", "TSLA", "Tesla"],
    "CPNG": ["쿠팡", "CPNG", "Coupang"],
    "KMB": ["킴벌리", "KMB", "Kimberly"],
    # 금 및 자산
    "GOLD": ["금", "금값", "금시세", "Gold", "KRX금"],
    "1659.N": ["금", "금값", "금시세", "Gold", "KRX금"],
    "GC=F": ["금", "금값", "금시세", "Gold"],
    # 국내 주식
    "003670": ["포스코퓨처엠", "포스코", "퓨처엠", "POSCO"],
    "012450": ["한화에어로스페이스", "한화에어로", "에어로스페이스"],
    "079550": ["LIG넥스원", "LIG", "넥스원"],
    "489790": ["한화비전", "비전"],
    "064350": ["현대로템", "로템"],
}


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
  if not text or "개별 주요 뉴스 없음" in text or "오류" in text:
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
    res = session.get(url, timeout=5, headers=YAHOO_HEADERS)
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


def get_period_rate(ticker, range_str="5d"):
  """기간별(5d/1mo 등) 누적 등락률 계산.

  기존에는 5일 등락률 하나만 계산해서 '오늘/1주일/1달' 문구에 전부
  재사용했습니다. 여기서는 range_str을 바꿔가며 실제 1개월 데이터도
  따로 뽑을 수 있게 분리했습니다.
  """
  url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_str}"
  try:
    res = session.get(url, timeout=5, headers=YAHOO_HEADERS)
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


def get_5d_rate(ticker):
  """최근 5일간 누적 등락률 계산 (하위 호환용 래퍼)"""
  return get_period_rate(ticker, "5d")


def get_1mo_rate(ticker):
  """최근 1개월간 누적 등락률 계산"""
  return get_period_rate(ticker, "1mo")


def get_naver_domestic_price(code):
  """국내 주식 가격 조회"""
  try:
    api_url = f"https://m.stock.naver.com/api/stock/{code}/basic"
    res = session.get(api_url, timeout=5, headers=NAVER_HEADERS)
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
    res = session.get(api_url, timeout=5, headers=NAVER_HEADERS)
    if res.status_code == 200:
      jdata = res.json()
      price = float(jdata.get("closePrice", "0").replace(",", ""))
      rate = float(jdata.get("fluctuationsRatio", "0"))
      return price, rate
  except Exception as e:
    print(f"네이버 금 시세 에러: {e}")
  return 0.0, 0.0


def get_recent_yahoo_news_direct(ticker, keywords):
  """[지침 1, 2 반영] 야후 뉴스를 조회하고 키워드로 1차 검증 후 반환"""
  try:
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}&newsCount=10"
    res = session.get(url, timeout=5, headers=YAHOO_HEADERS)
    if res.status_code == 200:
      news_list = res.json().get("news", [])
      current_time = int(time.time())
      one_day_ago = current_time - (24 * 60 * 60)

      # 1차 키워드 검증 (지침 1)
      for item in news_list:
        title = item.get("title", "")
        pub_time = item.get("providerPublishTime", 0)

        if title and any(kw.lower() in title.lower() for kw in keywords):
          translated = translate_to_korean(title)
          if pub_time >= one_day_ago:
            return translated
          else:
            return f"{translated} (최근 소식)"
  except Exception as e:
    print(f"야후 다이렉트 뉴스 에러 ({ticker}): {e}")

  # 키워드 일치 뉴스 부재 시 Fallback 메시지 (지침 2)
  return "개별 주요 뉴스 없음 (증시 전반 흐름 동반)"


def _extract_title(item):
  """뉴스 항목 dict에서 제목으로 보이는 필드를 최대한 유연하게 찾아낸다.

  네이버 비공식 API는 필드명이 예고 없이 바뀌는 경우가 많아서, 알려진
  키 이름들을 먼저 시도하고, 그래도 없으면 '문자열이면서 어느 정도
  길이가 있는 값'을 제목 후보로 사용한다.
  """
  known_keys = (
      "tit", "title", "articleTitle", "sntnc",
      "newsTitle", "subject", "headline",
  )
  for key in known_keys:
    val = item.get(key)
    if isinstance(val, str) and val.strip():
      return val

  for val in item.values():
    if isinstance(val, str) and len(val.strip()) >= 6:
      return val
  return None


def _extract_items(data):
  """네이버 뉴스 API 응답에서 리스트를 최대한 유연하게 뽑아낸다."""
  if isinstance(data, list):
    return data
  if isinstance(data, dict):
    for key in ("items", "newsList", "list", "result", "data", "contents"):
      val = data.get(key)
      if isinstance(val, list):
        return val
      # result가 다시 dict를 감싸고 있는 경우 (e.g. {"result": {"items": [...]}})
      if isinstance(val, dict):
        for inner_key in ("items", "newsList", "list"):
          inner_val = val.get(inner_key)
          if isinstance(inner_val, list):
            return inner_val
  return []


def get_naver_news(code, is_us=False, keywords=None):
  """[지침 1, 2 반영] 네이버 뉴스를 조회하고 키워드로 1차 검증 후 반환"""
  keywords = keywords or []
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

      api_url = f"https://m.stock.naver.com/api/news/world/stock/{naver_symbol}?pageSize=10&page=1"
    else:
      api_url = (
          f"https://m.stock.naver.com/api/news/stock/{code}?pageSize=10&page=1"
      )

    res = session.get(api_url, timeout=5, headers=NAVER_HEADERS)

    if DEBUG_NEWS:
      print(f"[뉴스 디버그] {code} status={res.status_code} url={api_url}")

    if res.status_code != 200:
      return "개별 주요 뉴스 없음 (증시 전반 흐름 동반)"

    data = res.json()
    items = _extract_items(data)

    if DEBUG_NEWS:
      if items:
        print(
            f"[뉴스 디버그] {code} 수신 {len(items)}건, "
            f"첫 항목 keys={list(items[0].keys())}"
        )
      else:
        top_keys = list(data.keys()) if isinstance(data, dict) else type(data)
        print(f"[뉴스 디버그] {code} items 비어있음. 응답 최상위 구조={top_keys}")
        print(f"[뉴스 디버그] {code} 원본 응답(앞 300자)={json.dumps(data, ensure_ascii=False)[:300]}")

    # 1차: 키워드와 일치하는 뉴스를 우선 반환
    for item in items:
      title = _extract_title(item)
      if title:
        clean_t = clean_html(title)
        if any(kw.lower() in clean_t.lower() for kw in keywords):
          return clean_t

    # 2차: 키워드 일치가 하나도 없으면, 그래도 뉴스 자체는 존재하니
    # 최신 뉴스 1건이라도 보여준다 (완전 무소식보다 유용).
    if items:
      title = _extract_title(items[0])
      if title:
        return f"{clean_html(title)} (키워드 미일치, 최신 소식)"

  except Exception as e:
    print(f"네이버 뉴스 수집 에러 ({code}): {e}")

  # 응답 자체가 비어있거나 실패한 경우의 Fallback 메시지 (지침 2)
  return "개별 주요 뉴스 없음 (증시 전반 흐름 동반)"


def generate_technical_strategy(rate_5d, rate_1mo=None):
  """5일/1개월 누적 등락률 기반 분석.

  기존 코드는 5일 등락률 '하나'로 오늘/1주일/1달 문구를 전부 만들었습니다.
  여기서는 1개월치 실측 등락률(rate_1mo)이 주어지면 '1달' 코멘트에는
  그 값을 실제로 반영합니다. rate_1mo가 없으면 기존처럼 5일치로만 판단합니다.
  """
  if rate_1mo is None:
    rate_1mo = rate_5d

  def bucket(rate):
    if rate <= -3.0:
      return "oversold"
    elif rate >= 3.0:
      return "overheated"
    return "sideways"

  today_bucket = bucket(rate_5d)      # '오늘' 판단 기준: 최근 5일 흐름
  week_bucket = bucket(rate_5d)       # '1주일' 판단 기준: 동일하게 최근 5일 흐름
  month_bucket = bucket(rate_1mo)     # '1달' 판단 기준: 실제 1개월 누적 등락률

  today_action = {
      "oversold": "분할 매수 고려",
      "overheated": "추격 매수 자제",
      "sideways": "관망 또는 지지선 분할 접근",
  }[today_bucket]

  week_action = {
      "oversold": "저점 매집",
      "overheated": "일부 이익 실현 검토",
      "sideways": "횡보 대응",
  }[week_bucket]

  month_action = {
      "oversold": "반등 추이 관망",
      "overheated": "홀딩",
      "sideways": "비중 유지",
  }[month_bucket]

  return (
      f"💡 기술적 분석: 5일 {rate_5d:+,.2f}% / 1개월 {rate_1mo:+,.2f}%\n"
      f"  - ⏱ 타이밍 ▶ 오늘: {today_action} | 1주일: {week_action} | "
      f"1달: {month_action}"
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
  keywords = STOCK_KEYWORDS.get(symbol_or_code, [name])

  if is_us:
    cp, rate = get_yahoo_us_price(symbol_or_code)
    yahoo_headline = get_recent_yahoo_news_direct(symbol_or_code, keywords)
    naver_headline = get_naver_news(symbol_or_code, is_us=True, keywords=keywords)
    rate_5d = get_period_rate(symbol_or_code, "5d")
    rate_1mo = get_period_rate(symbol_or_code, "1mo")
    price_str = f"${cp:,.2f} ({rate:+,.2f}%)" if cp > 0 else "가격 수집 실패"

    news_block = (
        f"  - 📰 야후(번역): {yahoo_headline}\n"
        f"  - 📰 네이버: {naver_headline}\n"
    )

  elif is_gold:
    cp, rate = get_naver_gold_price()
    naver_headline = get_naver_news("1659.N", is_us=False, keywords=keywords)
    rate_5d = get_period_rate("GC=F", "5d")
    rate_1mo = get_period_rate("GC=F", "1mo")
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
    naver_headline = get_naver_news(symbol_or_code, is_us=False, keywords=keywords)
    rate_5d = get_period_rate(yahoo_code, "5d")
    rate_1mo = get_period_rate(yahoo_code, "1mo")
    price_str = f"{cp:,.0f}원 ({rate:+,.2f}%)" if cp > 0 else "가격 수집 실패"

    news_block = f"  - 📰 네이버 소식: {naver_headline}\n"

  strategy = generate_technical_strategy(rate_5d, rate_1mo)
  return f"• {name} | {price_str}\n{news_block}  -{strategy}\n"


def main():
  print(
      "🔄 [에이전트 가동] 키워드 검증 및 예외처리가 강화된 브리핑 수집을"
      " 시작합니다..."
  )
  if DEBUG_NEWS:
    print("🐞 DEBUG_NEWS=1 : 네이버 뉴스 API 원본 응답 구조를 출력합니다.")

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

  print("✅ 신뢰도 높은 주식 브리핑 전송 완료!")


if __name__ == "__main__":
  main()
