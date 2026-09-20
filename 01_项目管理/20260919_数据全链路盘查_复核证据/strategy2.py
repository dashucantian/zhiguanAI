import zipfile,re,sys
sys.stdout.reconfigure(encoding="utf-8")
p=r"D:\Project\zhiguanAI\01_项目管理\战略\止观AI三年总体战略方案.docx"
z=zipfile.ZipFile(p)
xml=z.read("word/document.xml").decode("utf-8")
txt=re.sub(r"<[^>]+>","",re.sub(r"</w:p>","\n",xml))
lines=[l.strip() for l in txt.split("\n") if l.strip()]
for a,b in [(85,150),(190,265)]:
    print(f"\n########## paragraphs {a}-{b} ##########")
    for i in range(a,min(b,len(lines))): print(f"{i:4}: {lines[i][:200]}")
