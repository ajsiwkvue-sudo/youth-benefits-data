# youth-benefits-data

청년 혜택 지도에 쓸 공공 API 데이터를 매일 모으는 저장소.

- 매일 06:30 (한국 시간) GitHub Actions가 `fetch.py`를 실행해 `data/*.json`을 갱신함
- 청년 혜택 지도 루틴(08:00)이 아래 주소에서 파일을 받아 페이지 데이터를 갱신함
  - `https://raw.githubusercontent.com/ajsiwkvue-sudo/youth-benefits-data/main/data/status.json`
  - `https://raw.githubusercontent.com/ajsiwkvue-sudo/youth-benefits-data/main/data/<출처>.json`
- 이 저장소에는 공공 데이터와 수집 코드만 둠. 개인정보는 넣지 않음

## 출처와 필요한 비밀값

| 파일 | 내용 | 비밀값 |
|---|---|---|
| `youthcenter.json` | 온통청년 청년정책 전체 | `YOUTHCENTER_KEY` |
| `gov24.json` | 보조금24 공공서비스 중 '청년' 포함 | `DATA_GO_KR_KEY` |
| `welfare_national.json` | 중앙부처 복지서비스, 청년 검색 | `DATA_GO_KR_KEY` |
| `welfare_local.json` | 서울 지자체 복지서비스, 청년 검색 | `DATA_GO_KR_KEY` |
| `lh_notices.json` | LH 분양·임대 공고, 서울 | `DATA_GO_KR_KEY` |
| `applyhome.json` | 청약홈 분양정보, 서울 | `DATA_GO_KR_KEY` |
| `seoul_culture.json` | 서울 문화행사 중 '청년' 포함 | `SEOUL_KEY` |
| `seoul_edu.json` | 서울 공공서비스예약 교육 중 '청년' 포함 | `SEOUL_KEY` |

비밀값 넣기 (키는 채팅이나 파일에 적지 말고 터미널에서 직접 입력) :

```bash
gh secret set YOUTHCENTER_KEY -R ajsiwkvue-sudo/youth-benefits-data
gh secret set DATA_GO_KR_KEY  -R ajsiwkvue-sudo/youth-benefits-data
gh secret set SEOUL_KEY       -R ajsiwkvue-sudo/youth-benefits-data
gh workflow run fetch -R ajsiwkvue-sudo/youth-benefits-data   # 바로 한 번 돌려 보기
```

공공데이터포털 키는 API마다 '활용신청'을 해야 같은 키로 호출됨.

## 상태 확인

`data/status.json`에 출처별 상태가 남음 : `ok`(건수), `no_key`(비밀값 없음), `error`(오류 문구, 키는 가림).
실패한 출처는 이전 데이터 파일을 지우지 않음.

## 확인 안 된 것

요청 파라미터와 응답 필드 이름 일부는 키 없이 만든 것이라, 키를 넣고 첫 실행 결과를 보고 고쳐야 함
(특히 복지서비스 `srchKeyCode`·`ctpvNm`, LH `CNP_CD`, 청약홈 `cond` 조건).
