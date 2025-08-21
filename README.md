# SSTI-Hunter  

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)  
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)  
[![Issues](https://img.shields.io/github/issues/TobiasGuta/FuzzTI)](https://github.com/tobiasGuta/FuzzTI/issues)  
[![Stars](https://img.shields.io/github/stars/TobiasGuta/FuzzTI?style=social)](https://github.com/TobiasGuta/FuzzTI)  

**SSTI-Hunter** is a Python tool to **detect and fingerprint Server-Side Template Injection (SSTI) vulnerabilities**.  
It automates reflection testing, evaluates payloads, and applies a **decision-tree fingerprinting method** to identify the underlying template engine (Jinja2, Twig, Smarty, Mako, etc).  

---

## Features
- Detects reflection of special characters in query & path params.  
- Supports **GET / POST** requests.  
- Rich terminal output (colored tables, clear results).  
- Decision-tree engine fingerprinting.  
- Helps confirm if a target is exploitable or just reflecting payloads.  

---

## Installation
```bash
git clone https://github.com/tobiasGuta/FuzzTI.git
cd FuzzTI
pip install -r requirements.txt
```

## Usage

```bash
python3 ssti_hunter.py http://target.com/profile/anything -f chars.txt
```

**Arguments:**

-   `url` → Full target URL (e.g., `http://127.0.0.1:5000/profile/anything`)

-   `-f, --file` → File containing characters to test

## 📌 Example Output

```bash
───────────────────────── SSTI Payload Test ─────────────────────────
Payload     Method   Input Type   Status   Result
{{7*7}}     GET      query        200      💀 SSTI Detected! → 49
${7*7}      GET      query        200      Not reflected/evaluated

───────────────────────── Template Engine Fingerprint ─────────────────────────
Payload     Result      Engine Candidate
${7*7}      ✘ No match  -
{{7*7}}     ✔ 49        Match
{{7*'7'}}   ✘ No match  -
──────────────────────────────────────────────────────────────────────────────
[+] Likely template engine: Jinja2/Twig

🎯 Decision Tree Explained
${7*7}
   ├─ works → test Smarty/Mako payloads
   │   ├─ a{*comment*}b works → Smarty
   │   └─ ${"z".join("ab")} works → Mako
   └─ fails → try {{7*7}}
         ├─ works → test {{7*'7'}}
         │   ├─ works → Jinja2
         │   └─ fails → Twig/unknown
         └─ fails → Not vulnerable

```
Disclaimer
----------

This project is for **educational and authorized security testing only**.\
I am not responsible for any misuse or damage caused by this tool.

* * * * *

Contributing
---------------

Pull requests are welcome! If you'd like to improve detection logic, add new payloads, or enhance fingerprinting, feel free to submit a PR.
