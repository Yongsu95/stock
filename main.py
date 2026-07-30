from datetime import datetime
import json
import requests
import urllib3
import yfinance as yf
from token_manager import get_access_token

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def main():
  print("🔄 [에이전트 가동] 시장 데이터와 외신 뉴스를 수집합니다...")
  today_str = datetime.now().strftime("%Y년 %m월 %d일")

  # 대상 종목 및 야후 파이낸스 티커 매핑
  tickers = {
      "킴벌리클라크": "KMB",
      "테슬라": "TSLA",
      "쿠팡": "CPNG",
      "금": "GC=F",
      "포스코퓨처엠": "003670.KS",
      "한화에어로스페이스": "012450.KS",
      "LIG넥스원": "079550.KS",
      "한화비전": "471370.KS",
      "현대로템": "064350.KS",
  }

  report = [f"📊 [{today_str} 맞춤형 인텔리전스 브리핑]\n"]

  # 1. 미국 장 마감 시황 (테슬라, 쿠팡, 킴벌리클라크)
  report.append("🇺🇸 [미국 장 마감 시황]")
  us_stocks = ["테슬라", "쿠팡", "킴벌리클라크"]

  for name in us_stocks:
    try:
      tk = yf.Ticker(tickers[name])
      hist = tk.history(period="2d")
      news_list = tk.news
      headline = (
          news_list[0].get("title", "최신 뉴스 없음")
          if news_list
          else "최신 뉴스 없음"
      )

      if not hist.empty:
        cp = hist["Close"].iloc[-1]
        pp = hist["Close"].iloc[-2]
        rate = ((cp - pp) / pp) * 100
        price_str = f"${cp:,.2f} ({rate:+,.2f}%)"
      else:
        price_str = "가격 정보 없음"

      # 사용자 핵심 투자 전략 반영
      if name == "테슬라":
        strategy = (
            "💡 전략: 4분기 메가팩 및 FSD 모멘텀 기대\n  - ⏱ 타이밍 ▶ 오늘:"
            " 분할 매수 유지 | 1주일: 비중 확대 | 1달: 홀딩"
        )
      elif name == "쿠팡":
        strategy = (
            "💡 전략: 펀더멘털 이슈 대응, 본절 탈출 목표\n  - ⏱ 타이밍"
            " ▶ 오늘: 모니터링 | 1주일: 유지 | 1달: 목표가 대응"
        )
      else:
        strategy = (
            "💡 전략: 방어주 포트폴리오 안전판 유지\n  - ⏱ 타이밍 ▶ 오늘: 관망 |"
            " 1주일: 분할 접근 | 1달: 홀딩"
        )

      report.append(
          f"• {name} | {price_str}\n  - 📰 외신: {headline}\n  - {strategy}\n"
      )
    except Exception:
      report.append(f"• {name}: 데이터 수집 에러\n")

  # 2. 국내 장 및 자산 실시간 시황 (금, 방산 4인방, 포스코퓨처엠)
  report.append("\n🇰🇷 [국내 장 실시간 시황 & 핵심 자산]")
  kr_assets = [
      "금",
      "포스코퓨처엠",
      "한화에어로스페이스",
      "LIG넥스원",
      "한화비전",
      "현대로템",
  ]

  for name in kr_assets:
    try:
      tk = yf.Ticker(tickers[name])
      hist = tk.history(period="2d")
      news_list = tk.news
      headline = (
          news_list[0].get("title", "동향 없음")
          if news_list
          else "동향 없음"
      )

      if not hist.empty:
        cp = hist["Close"].iloc[-1]
        pp = hist["Close"].iloc[-2]
        rate = ((cp - pp) / pp) * 100
        price_str = (
            f"{cp:,.2f} (국제금)"
            if name == "금"
            else f"{cp:,.0f}원 ({rate:+,.2f}%)"
        )
      else:
        price_str = "가격 정보 없음"

      # 방산 및 이차전지, 금 운용 전략 반영
      if (
          "방산" in name
          or name in ["한화에어로스페이스", "LIG넥스원", "한화비전", "현대로템"]
      ):
        strategy = (
            "💡 전략: 지정학적 리스크 및 수주 잔고 기반 장기 보유\n  -"
            " ⏱ 타이밍 ▶ 오늘: 분할 매수 평단가 조율 | 1주일: 눌림목 대응"
            " | 1달: 장기 보유"
        )
      elif name == "포스코퓨처엠":
        strategy = (
            "💡 전략: 2차전지 성장주 저점 분할 매수\n  - ⏱ 타이밍 ▶"
            " 오늘: 저점 매수 | 1주일: 반등 시 대응 | 1달: 적립식 매집"
        )
      else:
        strategy = (
            "💡 전략: 포트폴리오의 든든한 안전판(금) 유지\n  - ⏱ 타이밍"
            " ▶ 오늘: 분할 매수 | 1주일: 홀딩 | 1달: 비중 유지"
        )

      report.append(
          f"• {name} | {price_str}\n  - 📰 동향: {headline}\n  - {strategy}\n"
      )
    except Exception:
      report.append(f"• {name}: 데이터 수집 에러\n")

  final_text = "\n".join(report)

  # 3. 신선하게 발급받은 액세스 토큰으로 카카오톡 전송
  access_token = get_access_token()
  if not access_token:
    print("❌ 유효한 액세스 토큰을 가져오지 못해 전송을 중단합니다.")
    return

  url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
  headers = {"Authorization": f"Bearer {access_token}"}
  text_message = {
      "object_type": "text",
      "text": final_text,
      "link": {
          "web_url": "https://finance.naver.com",
          "mobile_web_url": "https://finance.naver.com",
      },
      "button_title": "네이버 금융 확인하기",
  }
  data = {"template_object": json.dumps(text_message)}

  response = requests.post(url, headers=headers, data=data, verify=False)

  if response.status_code == 200:
    print("✅ [성공] 토큰 자동 갱신 및 맞춤형 브리핑 전송 완료!")
  else:
    print(f"❌ 전송 실패: {response.status_code}, {response.json()}")


if __name__ == "__main__":
  main()