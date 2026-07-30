import json
import os
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_access_token():
  """로컬 환경(json) 또는 클라우드 환경(환경변수)에서 토큰을 읽어

  리프레시 토큰을 이용해 최신 액세스 토큰을 발급받습니다.
  """
  rest_api_key = None
  refresh_token = None

  # 1. 클라우드 환경변수에 키가 등록되어 있다면 우선 사용 (무중단 대비)
  if os.environ.get("REST_API_KEY") and os.environ.get("REFRESH_TOKEN"):
    rest_api_key = os.environ.get("REST_API_KEY")
    refresh_token = os.environ.get("REFRESH_TOKEN")
  else:
    # 2. 로컬 환경일 경우 kakao_tokens.json 파일에서 로드
    try:
      with open("kakao_tokens.json", "r") as fp:
        tokens = json.load(fp)
        # 본인의 카카오 앱 REST API 키를 여기에 넣거나 딕셔너리로 관리
        # (안전하게 kakao_tokens에 rest_api_key도 함께 저장해두거나 아래에 직접 입력 가능)
        refresh_token = tokens.get("refresh_token")
        rest_api_key = tokens.get(
            "rest_api_key", "483acfaff219ef23a5df2456cc622dc4"
        )
    except Exception as e:
      print(f"❌ 토큰 파일 로드 실패: {e}")
      return None

  # 카카오 인증 서버에 새 액세스 토큰 발급 요청
  url = "https://kauth.kakao.com/oauth/token"
  data = {
      "grant_type": "refresh_token",
      "client_id": rest_api_key,
      "refresh_token": refresh_token,
  }

  response = requests.post(url, data=data, verify=False)
  if response.status_code == 200:
    result = response.json()
    new_access_token = result.get("access_token")
    return new_access_token
  else:
    print(f"❌ 액세스 토큰 갱신 에러: {response.status_code}")
    print(response.json())
    return None