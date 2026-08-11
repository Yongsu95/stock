      "🔄 [에이전트 가동] 키워드 검증 및 예외처리가 강화된 브리핑 수집을"
      " 시작합니다..."
  )
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
