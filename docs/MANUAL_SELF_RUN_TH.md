# คู่มือปฏิบัติการ (รันเอง ไม่ผ่าน Codex)

คู่มือนี้ใช้สำหรับ:
- ตรวจ/ยืนยันตัวเลขจากไฟล์ Google Drive ด้วย Gemini ผ่าน Chrome CDP
- อัปเดตไฟล์ข้อมูลเว็บ `docs/data/district_dashboard_data.json`
- validate และ deploy ขึ้น GitHub Pages (`main`)

## 1) โครงสร้างงานที่ต้องใช้

ใช้ 2 โฟลเดอร์:
- โค้ด OCR/CDP: `/Users/nat/dev/election`
- โค้ดเว็บ deploy: `/tmp/election-main`

สคริปต์หลัก:
- `/Users/nat/dev/election/drive_cdp_browser.py`
- `/tmp/election-main/scripts/validate_dashboard_data.py`

## 2) เตรียมระบบครั้งแรก

### 2.1 เตรียม Python env
```bash
cd /Users/nat/dev/election
python3 -m venv venv
./venv/bin/pip install -U pip
./venv/bin/pip install -r requirements.txt
```

### 2.2 เตรียม GitHub account ให้ push ได้
```bash
gh auth status -h github.com
gh auth switch -h github.com -u luengnat
gh auth setup-git -h github.com
```

## 3) เปิด Chrome CDP (2 พอร์ต ทำงานขนาน)

เปิด Chrome 2 instance:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp-9222
```

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9223 \
  --user-data-dir=/tmp/chrome-cdp-9223
```

ล็อกอิน Google Drive ในทั้ง 2 หน้าต่าง และเปิดไฟล์ PDF ที่ต้องการตรวจ

## 4) ตรวจว่า tab ถูกต้องก่อนถาม

```bash
cd /Users/nat/dev/election
./venv/bin/python drive_cdp_browser.py targets --devtools-url http://127.0.0.1:9222/json
./venv/bin/python drive_cdp_browser.py targets --devtools-url http://127.0.0.1:9223/json
```

ต้องเห็น URL ไฟล์ที่ต้องการจริง ถ้าไม่ใช่ ให้ `open --id ... --file` ใหม่

## 5) อ่านตัวเลขจากไฟล์ด้วย Gemini (แนะนำ)

### 5.1 เปิดไฟล์ตาม Drive file id
```bash
./venv/bin/python drive_cdp_browser.py open --devtools-url http://127.0.0.1:9222/json --id <FILE_ID_CONST> --file
./venv/bin/python drive_cdp_browser.py open --devtools-url http://127.0.0.1:9223/json --id <FILE_ID_PARTY> --file
```

### 5.2 ถามแบบ JSON (ตัวเลขอารบิก)
```bash
./venv/bin/python drive_cdp_browser.py ask-json \
  --devtools-url http://127.0.0.1:9222/json \
  --target-id <TARGET_ID_9222> \
  --wait-answer-seconds 45 \
  --question 'Return JSON only with Arabic numerals from sections 3.4, 4.1, 4.2, 4.3: {"total":int,"valid":int,"invalid":int,"blank":int}.'
```

> ถ้าไม่ตอบ/ค้าง:
- รัน `gemini` ก่อน 1 ครั้ง
- ถามซ้ำด้วย prompt สั้น: `.อ่านทีละบรรทัด`
- ถ้าเจอ `You’re offline` หรือ `Something went wrong` ให้ retry เดิม

### 5.3 Prompt ที่เสถียร
- ปกติ:  
  `Return JSON only with Arabic numerals from sections 3.4, 4.1, 4.2, 4.3: {"total":int,"valid":int,"invalid":int,"blank":int}.`
- fallback:
  `.อ่านทีละบรรทัด`

## 6) อัปเดตข้อมูลลงเว็บ

แก้ที่ไฟล์:
- `/tmp/election-main/docs/data/district_dashboard_data.json`

### 6.1 วิธีเร็ว (patch หลายเขตพร้อมกัน)
```bash
python3 - <<'PY'
import json, datetime
p='/tmp/election-main/docs/data/district_dashboard_data.json'
d=json.load(open(p,encoding='utf-8'))
now=datetime.datetime.now(datetime.timezone.utc).isoformat()

# ใส่ค่าที่ยืนยันแล้ว
updates={
  # (province, district_number, form_type): (valid, invalid, blank, total)
  ("นนทบุรี",6,"constituency"):(99026,3607,7390,110023),
  ("นนทบุรี",6,"party_list"):(103361,2576,4084,110021),
}

for r in d["items"]:
    k=(r.get("province"),r.get("district_number"),r.get("form_type"))
    if k not in updates:
        continue
    v,iv,b,t = updates[k]
    r["valid_votes_extracted"]=v
    r["invalid_votes"]=iv
    r["blank_votes"]=b
    r["total_votes_extracted"]=t
    r["total_votes"]=t
    rd=r.setdefault("sources",{}).setdefault("read",{})
    rd["valid_votes"]=v
    rd["invalid_votes"]=iv
    rd["blank_votes"]=b
    r["updated_by"]="manual"
    r["update_reason"]="manual_cdp_verified"
    r["updated_at"]=now

json.dump(d,open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("updated")
PY
```

## 7) ตรวจความถูกต้องก่อน push

### 7.1 validate schema/data
```bash
cd /tmp/election-main
python3 scripts/validate_dashboard_data.py --input docs/data/district_dashboard_data.json
```

### 7.2 เช็ค quick skew (รวมบัตร)
```bash
python3 - <<'PY'
import json
from collections import defaultdict
d=json.load(open('/tmp/election-main/docs/data/district_dashboard_data.json',encoding='utf-8'))['items']
by=defaultdict(dict)
for r in d:
  if r.get('form_type') in ('constituency','party_list'):
    by[(r.get('province'),r.get('district_number'))][r['form_type']]=r
for (p,k),g in sorted(by.items()):
  if 'constituency' not in g or 'party_list' not in g: continue
  c,p2=g['constituency'],g['party_list']
  vals=[c.get('valid_votes_extracted'),c.get('invalid_votes'),c.get('blank_votes'),
        p2.get('valid_votes_extracted'),p2.get('invalid_votes'),p2.get('blank_votes')]
  if any(v is None for v in vals): continue
  ct=c['valid_votes_extracted']+c['invalid_votes']+c['blank_votes']
  pt=p2['valid_votes_extracted']+p2['invalid_votes']+p2['blank_votes']
  dff=ct-pt
  if dff!=0 and abs(dff)<=2:
    print(f"{p} เขต {k}: {ct} vs {pt} ({dff:+d})")
PY
```

## 8) รันเว็บ local ตรวจด้วยสายตา

```bash
cd /tmp/election-main
python3 -m http.server 8080
```
เปิด `http://localhost:8080`

จุดตรวจหลัก:
- Winner Mismatch (ECT) ต้องเห็นเฉพาะ `แบ่งเขต`
- ค่า skew ต้องสอดคล้องกับ total ที่เพิ่งแก้
- เขตที่ยืนยันแล้วต้องไม่ย้อนกลับเป็นค่าจาก ECT fallback

## 9) Deploy ขึ้น production

```bash
cd /tmp/election-main
gh auth switch -h github.com -u luengnat
gh auth setup-git -h github.com

git add docs/data/district_dashboard_data.json docs/app-k16-r1.js docs/index.html
git commit -m "Update verified district totals"
git push origin HEAD:main
```

หลัง push:
- รอ GitHub Pages deploy
- hard refresh หน้าเว็บ (กัน cache JS/JSON)

## 10) Troubleshooting ที่เจอบ่อย

1. `Permission denied to ... natl-set`
- สลับ account:
  ```bash
  gh auth switch -h github.com -u luengnat
  gh auth setup-git -h github.com
  ```

2. Gemini ไม่ตอบ / ค้าง
- ใช้ `--target-id` ให้ตรง tab
- รัน `gemini` ก่อน แล้ว `ask-json` ซ้ำ
- ใช้ prompt `.อ่านทีละบรรทัด`

3. ได้คำตอบเป็นภาษา ไม่ใช่ JSON
- ย้ำ prompt ว่า `Return JSON only with Arabic numerals...`

4. ข้อมูลเว็บยังไม่เปลี่ยน
- เช็คว่าแก้ไฟล์ใน `/tmp/election-main/...` ไม่ใช่อีก repo
- hard refresh
- ตรวจว่า commit เข้า `main` แล้ว

5. Winner Mismatch โผล่บัญชีรายชื่อ
- ให้เช็คเวอร์ชัน JS ใน `index.html` และ logic ใน `app-k16-r1.js`
- ปัจจุบันตั้งให้ ECT mismatch แสดงเฉพาะ `constituency`

## 11) Check-list ก่อนปิดงาน

- [ ] ตัวเลขที่แก้มีหลักฐานจากไฟล์จริง (CDP/Gemini line-by-line)
- [ ] `valid + invalid + blank = total` ครบในแถวที่แก้
- [ ] validate script ผ่าน
- [ ] หน้า Winner Mismatch (ECT) มีเฉพาะแบ่งเขต
- [ ] commit/push ขึ้น `main` สำเร็จ

