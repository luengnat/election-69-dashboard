#!/usr/bin/env python3
"""
Province Google Drive folder URLs for 2026 Election ballot images.
Extracted from https://www.ect.go.th/ect_th/th/election-2026/
"""

# Format: Province name in Thai, English, Google Drive folder ID
PROVINCES = {
    # Northern Region (ภาคเหนือ)
    "north": [
        ("กำแพงเพชร", "Kamphaeng Phet", "1YFrEvow3-HwkcosJuXNeI82DL1WSrK_S"),
        ("แพร่", "Phrae", "1wD2ICNJHLhW0UaisZpW8ie49RC8Ba50v"),
        ("ลำปาง", "Lampang", "153yUnWv_2EWXSAbtsTTBE-wQYn9-6yXA"),
        ("เชียงใหม่", "Chiang Mai", "1RWvYL-2KyyyCKGjF6qj39qKkpUjI6oML"),
        ("พิษณุโลก", "Phitsanulok", "1I28S5sE3JOsbux5zk3oXp2gEe58-TpQ5"),
        ("ลำพูน", "Lamphun", "1nTVc_RgxSJIAHN2Zk3Y6KEbCteobL_bH"),
        ("เชียงราย", "Chiang Rai", "1w6ExwHN1c2qakXqUxAh7KmTJmZT-SSOo"),
        ("พิจิตร", "Phichit", "1At01M8EipiffkqpTRT2uln5FTcA-Mktj"),
        ("สุโขทัย", "Sukhothai", "1vDNUdsIBQUVVe1wX2sRfs-hzJ6g_eAkn"),
        ("น่าน", "Nan", "1Qxfkwmm98At95sWBoMStaYaUvGNh6jxd"),
        ("เพชรบูรณ์", "Phetchabun", "11xsNcsLAmjIIpBZu48FdjBFMerqQjNAQ"),
        ("อุตรดิตถ์", "Uttaradit", "1GBBRBIh-EmpHNwRXIoL8NYeftv6a-Zf2"),
        ("พะเยา", "Phayao", "1e_3_iZiijJIUxY20L55tZYW4AAXTnezQ"),
        ("แม่ฮ่องสอน", "Mae Hong Son", "1fPkBLx7rwoK9f6QRl6gwFxLzXYYpPSb8"),
    ],

    # Central Region (ภาคกลาง)
    "central": [
        ("กรุงเทพมหานคร", "Bangkok", "1C1bvoAzR55wuJ6Dkt5OYWGz4ukv-F5Sl"),
        ("ปทุมธานี", "Pathum Thani", "1bTPhst0RbMD-U9mFdxqOMzEyvOisQL6i"),
        ("สิงห์บุรี", "Sing Buri", "1SXJtGFdXWj5vptFftBaXYB0DRLKpRz2J"),
        ("ชัยนาท", "Chai Nat", "1UUm2NLLCM-2hwZ0-GyJ5FqP4-Kk2tBnx"),
        ("พระนครศรีอยุธยา", "Phra Nakhon Si Ayutthaya", "11kxwA_elo8-IzYgFyyxplpFymLlqz3eY"),
        ("สุพรรณบุรี", "Suphan Buri", "1t5GO6gg4W6rMGcO8pQOLYKLraVRUgAgR"),
        ("นครนายก", "Nakhon Nayok", "1P_419iJaH_wsCuKhOJXf0BpbbZ8CCxNG"),
        ("ลพบุรี", "Lop Buri", "1UdK2NnBS1b_g_F4NciQuCgZHAZusI370"),
        ("สระบุรี", "Saraburi", "1kjiOI6K37nvx8zDC0TRX-97JyOGY6SSu"),
        ("นครปฐม", "Nakhon Pathom", "1jPhEkJQc0icPWRl29xwxGx9koXwKO1A1"),
        ("สมุทรปราการ", "Samut Prakan", "15RY4_RDyMhgQWWmRANLg-Shh66L3Qq83"),
        ("อ่างทอง", "Ang Thong", "1pIq99HvFS-9AZ9MT1dWr6qV1kZG_bAmc"),
        ("นนทบุรี", "Nonthaburi", "1MApGQ8YpAG1hVMOWqfKdfag3KLWYYWY5"),
        ("สมุทรสงคราม", "Samut Songkhram", "1KLHjx-aovF3TTcFJdzzrt-nQ7-wWuzAc"),
        ("อุทัยธานี", "Uthai Thani", "1AEsdI9srCecTof5DeIAs9vYUay4KSzVH"),
        ("นครสวรรค์", "Nakhon Sawan", "1EE6JUZARf71n4j9UZyIkf82TquHgWUe0"),
        ("สมุทรสาคร", "Samut Sakhon", "1UJ_DgxRSWCcGzqsIQxA_vWgZqsZNncD1"),
    ],

    # Northeastern Region (ภาคตะวันออกเฉียงเหนือ)
    "northeast": [
        ("กาฬสินธุ์", "Kalasin", "1nRvDR4BWnW0j4DmeS4owe6Pb0iiUrudv"),
        ("มหาสารคาม", "Maha Sarakham", "1OLW1YTKxj4kTnxHYf0EdwZGKcE5Seojz"),
        ("ศรีสะเกษ", "Si Sa Ket", "14nCxcHcskvph2eBenG03XFAElTidJMZW"),
        ("ขอนแก่น", "Khon Kaen", "1A89Hil8Yu_cFlU-FPY6FLfevaqOEg5IC"),
        ("มุกดาหาร", "Mukdahan", "17r8Me6sljlN1NC7er3skOZfpbV1w4aE0"),
        ("หนองคาย", "Nong Khai", "1pgb4CNpWnsS7t487PHavovUYYmO0VzlJ"),
        ("ชัยภูมิ", "Chaiyaphum", "11OAVEt8A7SfQLv9uPi9O-gLk37i_3CSI"),
        ("ยโสธร", "Yasothon", "1eMX1g22UePTyLFRS3-GYQ-HSRyDC-_tm"),
        ("หนองบัวลำภู", "Nong Bua Lam Phu", "1JreB6tOF2w_8QkYActCc4182GBaEUH2u"),
        ("นครพนม", "Nakhon Phanom", "1KR8FtPU5ZSlQvIS-YAAdYzHALbYb-0fr"),
        ("ร้อยเอ็ด", "Roi Et", "1IRJHtBr1ohWfrotTcTbM_Ta39vSlkLkD"),
        ("อำนาจเจริญ", "Amnat Charoen", "14wkHdjHrTufhVFGsSY6rGT8Pst9HnjVu"),
        ("นครราชสีมา", "Nakhon Ratchasima", "1VUAH6skupn_Y1Kbfm5C6WYQSmSqsESNf"),
        ("เลย", "Loei", "1_MBbOA5r_HG5PA8dY8tzckP0nEzPPZcs"),
        ("อุดรธานี", "Udon Thani", "1picxYRg1bxW0QJyrTGG9zEV762sY--Kz"),
        ("บึงกาฬ", "Bueng Kan", "1KR8FtPU5ZSlQvIS-YAAdYzHALbYb-0fr"),
        ("สกลนคร", "Sakon Nakhon", "1EAH4dIYh2hgF0xXVTWNsRggtZS_2zaCD"),
        ("อุบลราชธานี", "Ubon Ratchathani", "1Nb7hJtDRoQy8VVR_cOfYhF7BHidRcuIH"),
        ("บุรีรัมย์", "Buri Ram", "1oPGf30Fo3_wELh5PpQibP24SXTVqga3q"),
        ("สุรินทร์", "Surin", "1CYvOxPmnWfImGLJyv5Nktx7R6uR7VV6j"),
    ],

    # Eastern Region (ภาคตะวันออก)
    "east": [
        ("จันทบุรี", "Chanthaburi", "15oWc6hB8XVJ4ku-fsCUQl7DI0bBOzl-a"),
        ("ตราด", "Trat", "1XLFjavED1BW_AG4xBDh5BfI6VQHv30_x"),
        ("สระแก้ว", "Sa Kaeo", "1JHP61jJf4ivKliXvS5kqZsAPz93lwujk"),
        ("ฉะเชิงเทรา", "Chachoengsao", "1GnQ8lFpzfnpuy83KItOp5X5uqYsz1Wit"),
        ("ปราจีนบุรี", "Prachin Buri", "1GnQ8lFpzfnpuy83KItOp5X5uqYsz1Wit"),
        ("ชลบุรี", "Chon Buri", "1tkp9vLv2nUSlECM4e9WnobfBr8RyTBzT"),
        ("ระยอง", "Rayong", "1uBC1GjNS_kmgemnO8HPZHO43oeNu1t1U"),
    ],

    # Western Region (ภาคตะวันตก)
    "west": [
        ("กาญจนบุรี", "Kanchanaburi", "1h98dubKjCGNWqajx-KZx-bXlACzg6B4X"),
        ("ประจวบคีรีขันธ์", "Prachuap Khiri Khan", "1pV61BgH_CEOM-ETOvssJcYJBrjsiNuuV"),
        ("ราชบุรี", "Ratchaburi", "1cbnTDoiRs1_BB60kx2nNlbUKkByOfNPI"),
        ("ตาก", "Tak", "19vRSFjNCdHx2SqCb1fpWqC1UguoTmCNx"),
        ("เพชรบุรี", "Phetchaburi", "1rLzQX8s86Dy5-gkSoaMr-fGfHOfyKOMj"),
    ],

    # Southern Region (ภาคใต้)
    "south": [
        ("กระบี่", "Krabi", "1jG2TcSJVrmvOacW0kMaDaVzrU2wM6Quc"),
        ("ปัตตานี", "Pattani", "1_y3m72ukRQM1kTa5XPR_qiQC6foLci5a"),
        ("ระนอง", "Ranong", "1Zwqe61yZx6F2ZcBaf4HcYYPSifBAJJhN"),
        ("ชุมพร", "Chumphon", "1Hhtc2g_Tr5cWt4mVeSKgx6GbP1ZpT85k"),
        ("พังงา", "Phangnga", "1OsTJ5mpr5BGxC29w-hUDmJztZQonU6mZ"),
        ("สตูล", "Satun", "1vSbfvVzsd6SCO2gIfw-AHuyJZqo9vovE"),
        ("ตรัง", "Trang", "1bQiDrKRbJ9seMVA6XlUhRFUw5sRMovrz"),
        ("พัทลุง", "Phatthalung", "1iZAbINx1SXfr50Ul5ljAc68Si7tDV9Sz"),
        ("สงขลา", "Songkhla", "1smYf3sOszd3onwYx-q1JthQ5_6bDgAjs"),
        ("นครศรีธรรมราช", "Nakhon Si Thammarat", "1Sn2_mAtcns6Q-Rn8QjlYdIYqvbiNt7DB"),
        ("ภูเก็ต", "Phuket", "1AsZpIJhIrt1XEmF8NASilMML_qf4We-C"),
        ("สุราษฎร์ธานี", "Surat Thani", "17P3jpRHAFCOlZOoo_z_XQRwqt34Ocd9P"),
        ("นราธิวาส", "Narathiwat", "1XRZIqhC4n6JEYCnON868am2pP4vMByE1"),
        ("ยะลา", "Yala", "1GWDOvgZI4njIepaFVQ-skYZ7LUxF-ylT"),
    ],
}

def get_all_provinces():
    """Get all provinces as a flat list."""
    all_provinces = []
    for region, provinces in PROVINCES.items():
        for province in provinces:
            all_provinces.append({
                "name_th": province[0],
                "name_en": province[1],
                "folder_id": province[2],
                "region": region
            })
    return all_provinces

def get_drive_url(folder_id):
    """Get Google Drive folder URL from folder ID."""
    return f"https://drive.google.com/drive/folders/{folder_id}"

if __name__ == "__main__":
    # Print all provinces
    all = get_all_provinces()
    print(f"Total provinces: {len(all)}")
    print("\n=== All Provinces ===")
    for p in all:
        print(f"{p['name_th']} ({p['name_en']}): {p['folder_id']}")

    # Print Phrae specifically (our test case)
    print("\n=== Phrae Test ===")
    phrae = next(p for p in all if p["name_en"] == "Phrae")
    print(f"Phrae folder ID: {phrae['folder_id']}")
    print(f"Phrae URL: {get_drive_url(phrae['folder_id'])}")
