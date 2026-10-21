# BADANG Trading 1.1

Bitget 공개 USDT 선물 데이터를 이용하는 단타·스윙 참고 신호 스캐너. 주문 기능이나 거래소 API 키가 없습니다.

## Render
Build: `pip install -r requirements.txt`
Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`

## 유의 사항
- 8종목씩 API를 순차 호출합니다. 전체 스캔은 오래 걸릴 수 있으며 Render 무료 서버가 잠들면 중단될 수 있습니다.
- Bitget API 형식이나 지역별 접근 제한에 따라 실패할 수 있습니다. 실패 종목 수를 별도로 표시합니다.
- 지표와 진입 시나리오는 예시로, 백테스트와 데이터 정합성 검증 전에는 실제 거래에 사용하지 마세요.
- 목표 손익비 2:1은 가정이며, 수수료/슬리피지/펀딩비가 제외되어 있습니다.
- 기존 1.0 파일을 교체하는 독립 버전입니다. 배포 전에 별도 브랜치 또는 백업을 권장합니다.


## 1.1 주요 코인 추가판
BTC/ETH/SOL/XRP/BNB/DOGE/ADA/LINK/AVAX/SUI를 거래대금 필터나 신호 여부와 무관하게 별도 조회합니다. Bitget USDT-FUTURES에 없는 종목 또는 API 오류는 오류로 표시합니다. '관망'은 매매 추천이 아닙니다.
