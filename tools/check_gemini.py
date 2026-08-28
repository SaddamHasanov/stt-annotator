"""Gemini API sağlamlıq yoxlaması — hansı modellər açarınızla işləyir.

İstifadə:  python tools/check_gemini.py
Açarı .env-dəki GEMINI_API_KEY-dən götürür.
"""
import json, os, sys, urllib.error, urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from ai.correct import load_env, call_gemini

# templates/index.html-dəki dropdown ilə eyni siyahı
DROPDOWN = [
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]


def list_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}&pageSize=200"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("models", [])


def main():
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key or key == "your_gemini_api_key_here":
        print("✗ .env faylında real GEMINI_API_KEY yoxdur.")
        return 1
    print(f"Açar: ...{key[-4:]}  (uzunluq {len(key)})\n")

    print("── 1. Açarın görə bildiyi modellər (ListModels) ──")
    try:
        models = list_models(key)
    except urllib.error.HTTPError as e:
        print(f"✗ ListModels alınmadı: {e.code} — {e.read().decode('utf-8', 'replace')[:300]}")
        return 1
    usable = {
        m["name"].removeprefix("models/")
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    }
    print(f"generateContent dəstəkləyən model sayı: {len(usable)}\n")

    print("── 2. Dropdown modellərinin canlı testi ──")
    rows = []
    for model in DROPDOWN:
        listed = "var" if model in usable else "YOX"
        res = call_gemini(
            'Return exactly this JSON and nothing else: {"ok": true}',
            "ping",
            model=model,
        )
        if res.get("success"):
            verdict, detail = "✓ İŞLƏYİR", ""
        else:
            verdict = "✗ XƏTA"
            detail = " ".join(str(res.get("error", "")).split())[:160]
        rows.append((model, listed, verdict, detail))
        print(f"  {model:<26} siyahıda:{listed:<4} {verdict}")
        if detail:
            print(f"      └─ {detail}")

    print("\n── Yekun ──")
    ok = [r[0] for r in rows if r[2].startswith("✓")]
    bad = [r[0] for r in rows if not r[2].startswith("✓")]
    print(f"  İşləyən: {', '.join(ok) if ok else '—'}")
    print(f"  İşləməyən: {', '.join(bad) if bad else '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
