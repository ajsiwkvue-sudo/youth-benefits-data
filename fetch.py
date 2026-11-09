"""청년 혜택 지도용 공공 API 수집기.

매일 GitHub Actions가 실행해 data/*.json 을 갱신한다. 키는 저장소 비밀값(환경변수)에서만 읽는다.
키가 없는 출처는 건너뛰고, 실패한 출처는 이전 데이터를 지우지 않고 status.json 에만 기록한다.
표준 라이브러리만 사용.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
UA = {"User-Agent": "youth-benefits-data/1.0 (+github actions)"}


def key(name):
    v = os.environ.get(name, "").strip()
    return v or None


def enc(k):
    """공공데이터포털 키는 '인코딩' 키를 넣어도 '디코딩' 키를 넣어도 되게."""
    return k if "%" in k else urllib.parse.quote(k, safe="")


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # 네트워크 오류는 잠시 뒤 다시 시도
            last = e
            time.sleep(3 * (i + 1))
    raise last


def xml_items(text, tag):
    root = ET.fromstring(text)
    err = root.find(".//returnAuthMsg")
    if err is not None and root.find(".//" + tag) is None:
        raise RuntimeError("API 오류 : " + (err.text or ""))
    return [{c.tag: (c.text or "").strip() for c in el} for el in root.iter(tag)]


def has_youth(d):
    return any("청년" in str(v) for v in d.values())


# ---------- 출처별 수집 (응답 필드 이름은 키 발급 후 실제 응답으로 확인 필요) ----------

YC_DROP = ("sprvsnInstPicNm", "operInstPicNm")  # 담당 공무원 이름은 공개 저장소에 올리지 않음


def yc_seoul(x):
    """zipCd(법정동 시군구 코드 목록)에 서울(11로 시작)이 있으면 서울 거주자도 받을 수 있는 정책. 전국 정책은 전 지역 코드가 들어 있음"""
    return any(c.strip().startswith("11") for c in (x.get("zipCd") or "").split(","))


def youthcenter(k):
    out, page, total = [], 1, None
    while page <= 200:
        u = ("https://www.youthcenter.go.kr/go/ythip/getPlcy?apiKeyNm=" + urllib.parse.quote(k)
             + "&pageNum=%d&pageSize=100&rtnType=json" % page)
        j = json.loads(get(u))
        if "errorCode" in j:
            raise RuntimeError("API 오류 : %s %s" % (j.get("errorCode"), j.get("errorMsg")))
        res = j.get("result", {})
        rows = res.get("youthPolicyList") or []
        out += rows
        total = int((res.get("pagging") or {}).get("totCount") or 0)
        if not rows or len(out) >= total:
            break
        page += 1
    if total and len(out) < total:
        raise RuntimeError("다 못 받음 : %d / %d건" % (len(out), total))
    seoul = [{kk: vv for kk, vv in x.items() if kk not in YC_DROP} for x in out if yc_seoul(x)]
    youthcenter.note = "전국 %d건 중 서울 거주자 대상 %d건만 저장" % (len(out), len(seoul))
    return seoul


def gov24(k):
    out, page = [], 1
    while page <= 40:
        u = "https://api.odcloud.kr/api/gov24/v3/serviceList?page=%d&perPage=500&serviceKey=%s" % (page, enc(k))
        j = json.loads(get(u))
        if j.get("code", 0) < 0:
            raise RuntimeError("API 오류 : %s" % j.get("msg"))
        rows = j.get("data") or []
        out += [r for r in rows if has_youth(r)]
        if not rows or page * 500 >= int(j.get("totalCount") or 0):
            break
        page += 1
    return out


def welfare_national(k):
    u = ("https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001?serviceKey=%s"
         "&callTp=L&pageNo=1&numOfRows=500&srchKeyCode=003&searchWrd=%s" % (enc(k), urllib.parse.quote("청년")))
    return xml_items(get(u), "servList")


def welfare_local(k):
    u = ("https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist?serviceKey=%s"
         "&pageNo=1&numOfRows=500&ctpvNm=%s&searchWrd=%s" % (enc(k), urllib.parse.quote("서울특별시"), urllib.parse.quote("청년")))
    return xml_items(get(u), "servList")


def lh_notices(k):
    u = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1?serviceKey=%s&PG_SZ=100&PAGE=1&CNP_CD=11" % enc(k)
    j = json.loads(get(u))
    if isinstance(j, dict) and "OpenAPI_ServiceResponse" in j:
        raise RuntimeError("API 오류 : %s" % j["OpenAPI_ServiceResponse"])
    rows = []
    for part in (j if isinstance(j, list) else [j]):
        for v in (part.values() if isinstance(part, dict) else []):
            if isinstance(v, list):
                rows += [r for r in v if isinstance(r, dict)]
    return rows


def applyhome(k):
    cond = urllib.parse.quote("cond[SUBSCRPT_AREA_CODE_NM::EQ]") + "=" + urllib.parse.quote("서울")
    u = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?page=1&perPage=200&%s&serviceKey=%s" % (cond, enc(k))
    j = json.loads(get(u))
    if j.get("code", 0) < 0:
        raise RuntimeError("API 오류 : %s" % j.get("msg"))
    return j.get("data") or []


def seoul(service):
    """서울 열린데이터광장 : 한 번에 1,000건까지라 나눠 받고, 오류는 XML로 오므로 따로 읽음."""
    def run(k):
        out, start, total = [], 1, None
        while start <= 30000:
            u = "http://openapi.seoul.go.kr:8088/%s/json/%s/%d/%d/" % (urllib.parse.quote(k), service, start, start + 999)
            text = get(u).strip()
            if text.startswith("<"):
                root = ET.fromstring(text)
                raise RuntimeError("API 오류 : %s %s" % (root.findtext(".//CODE"), (root.findtext(".//MESSAGE") or "").strip()[:120]))
            j = json.loads(text)
            body = j.get(service) or {}
            res = body.get("RESULT") or j.get("RESULT") or {}
            if res.get("CODE") not in (None, "INFO-000"):
                if res.get("CODE") == "INFO-200":  # 해당 데이터 없음
                    break
                raise RuntimeError("API 오류 : %s %s" % (res.get("CODE"), res.get("MESSAGE")))
            rows = body.get("row") or []
            out += [r for r in rows if has_youth(r)]
            total = int(body.get("list_total_count") or 0)
            start += 1000
            if not rows or start > total:
                break
        return out
    return run


SOURCES = [
    # 이름, 필요한 비밀값, 수집 함수, 설명
    ("youthcenter", "YOUTHCENTER_KEY", youthcenter, "온통청년 청년정책 중 서울 거주자가 받을 수 있는 것"),
    ("gov24", "DATA_GO_KR_KEY", gov24, "보조금24 공공서비스 중 '청년' 포함"),
    ("welfare_national", "DATA_GO_KR_KEY", welfare_national, "중앙부처 복지서비스, 청년 검색"),
    ("welfare_local", "DATA_GO_KR_KEY", welfare_local, "서울 지자체 복지서비스, 청년 검색"),
    ("lh_notices", "DATA_GO_KR_KEY", lh_notices, "LH 분양·임대 공고, 서울"),
    ("applyhome", "DATA_GO_KR_KEY", applyhome, "청약홈 분양정보, 서울"),
    ("seoul_culture", "SEOUL_KEY", seoul("culturalEventInfo"), "서울 문화행사 중 '청년' 포함"),
    ("seoul_edu", "SEOUL_KEY", seoul("ListPublicReservationEducation"), "서울 공공서비스예약 교육 중 '청년' 포함"),
]


def main():
    os.makedirs(DATA, exist_ok=True)
    now = datetime.now(KST).isoformat(timespec="seconds")
    status_path = os.path.join(DATA, "status.json")
    try:
        status = json.load(open(status_path, encoding="utf-8"))
    except Exception:
        status = {}
    status["run_at"] = now
    status.setdefault("sources", {})
    for name, secret, fn, desc in SOURCES:
        k = key(secret)
        prev = status["sources"].get(name, {})
        if not k:
            status["sources"][name] = {**prev, "desc": desc, "state": "no_key", "checked_at": now,
                                       "note": "비밀값 %s 없음" % secret}
            print("skip %-16s (no %s)" % (name, secret))
            continue
        try:
            rows = fn(k)
            with open(os.path.join(DATA, name + ".json"), "w", encoding="utf-8") as f:
                json.dump({"source": name, "desc": desc, "fetched_at": now, "count": len(rows), "items": rows},
                          f, ensure_ascii=False, indent=1)
            status["sources"][name] = {"desc": desc, "state": "ok", "checked_at": now, "fetched_at": now, "count": len(rows)}
            if getattr(fn, "note", None):
                status["sources"][name]["note"] = fn.note
            print("ok   %-16s %d" % (name, len(rows)))
        except Exception as e:
            msg = str(e)
            for s in (k, enc(k)):
                msg = msg.replace(s, "***")  # 오류 문구에 키가 섞여 나오지 않게
            status["sources"][name] = {**prev, "desc": desc, "state": "error", "checked_at": now, "error": msg[:300]}
            print("fail %-16s %s" % (name, msg[:200]))
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
