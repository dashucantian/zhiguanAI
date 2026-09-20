import zipfile,re,sys,glob,os
sys.stdout.reconfigure(encoding="utf-8")
for p in glob.glob(r"D:\Project\zhiguanAI\*.docx")+glob.glob(r"D:\Project\zhiguanAI\01_项目管理\**\*.docx",recursive=True):
    if "60" in os.path.basename(p) or "样本" in os.path.basename(p):
        try:
            z=zipfile.ZipFile(p); xml=z.read("word/document.xml").decode("utf-8")
            txt=re.sub(r"<[^>]+>","",re.sub(r"</w:p>","\n",xml))
            lines=[l.strip() for l in txt.split("\n") if l.strip()]
            print(f"\n##### {os.path.basename(p)} paragraphs={len(lines)}")
            for i,l in enumerate(lines[:80]):
                if any(k in l for k in ("60","150","样本","禅师","标注","标准")):
                    print(f"  {i}: {l[:200]}")
        except Exception as e: print(p,"ERR",e)
