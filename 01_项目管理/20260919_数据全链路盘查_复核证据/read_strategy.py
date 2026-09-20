import zipfile,re,sys,os
sys.stdout.reconfigure(encoding="utf-8")
p=r"D:\Project\zhiguanAI\01_项目管理\战略\止观AI三年总体战略方案.docx"
z=zipfile.ZipFile(p)
xml=z.read("word/document.xml").decode("utf-8")
txt=re.sub(r"<[^>]+>","",re.sub(r"</w:p>","\n",xml))
lines=[l.strip() for l in txt.split("\n") if l.strip()]
print("total paragraphs:",len(lines))
# find key sections
for i,l in enumerate(lines):
    if any(k in l for k in ("第一年","关口","八项","清洗","标注","驾驶舱","60","150","样本")) and len(l)<200:
        print(f"{i:4}: {l[:190]}")
